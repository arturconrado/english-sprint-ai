import { writeFileSync } from "node:fs";
import { chromium } from "playwright";

const baseUrl = process.env.REALTIME_E2E_BASE_URL ?? "http://127.0.0.1:8000";
const fixturePath = "/tmp/english-sprint-authorized-tone.wav";

function createToneFixture(path) {
  const sampleRate = 48_000;
  const seconds = 2;
  const samples = sampleRate * seconds;
  const dataSize = samples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  for (let index = 0; index < samples; index += 1) {
    const value = Math.sin((2 * Math.PI * 440 * index) / sampleRate) * 0.08;
    buffer.writeInt16LE(Math.round(value * 32767), 44 + index * 2);
  }
  writeFileSync(path, buffer, { mode: 0o600 });
}

createToneFixture(fixturePath);
const browser = await chromium.launch({
  headless: true,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${fixturePath}`,
    "--autoplay-policy=no-user-gesture-required",
  ],
});

try {
  const context = await browser.newContext({
    permissions: ["microphone"],
    baseURL: baseUrl,
  });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/healthz`);
  const result = await page.evaluate(async () => {
    const peer = new RTCPeerConnection();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => peer.addTrack(track, stream));
    const events = peer.createDataChannel("oai-events");
    const remoteTrack = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("remote_audio_timeout")), 20_000);
      peer.ontrack = ({ track }) => {
        if (track.kind === "audio") {
          clearTimeout(timer);
          resolve(track.kind);
        }
      };
    });
    const responseDone = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("response_timeout")), 30_000);
      events.onmessage = ({ data }) => {
        const event = JSON.parse(data);
        if (event.type === "error") {
          clearTimeout(timer);
          reject(new Error("provider_event_error"));
        }
        if (event.type === "response.done") {
          clearTimeout(timer);
          resolve(event.type);
        }
      };
    });
    const open = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("data_channel_timeout")), 20_000);
      events.onopen = () => {
        clearTimeout(timer);
        resolve();
      };
    });
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    if (peer.iceGatheringState !== "complete") {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("ice_gathering_timeout")), 10_000);
        peer.addEventListener("icegatheringstatechange", () => {
          if (peer.iceGatheringState === "complete") {
            clearTimeout(timer);
            resolve();
          }
        });
      });
    }
    const created = await fetch("/v1/realtime/calls", {
      method: "POST",
      headers: {
        "Content-Type": "application/sdp",
        "X-Installation-Id": "github-actions-e2e-installation",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: peer.localDescription.sdp,
    });
    if (created.status !== 201) throw new Error(`create_failed_${created.status}`);
    const sessionId = created.headers.get("X-Voice-Session-Id");
    const location = created.headers.get("Location");
    if (!sessionId || !location) throw new Error("missing_internal_session_headers");
    const answer = await created.text();
    await peer.setRemoteDescription({ type: "answer", sdp: answer });
    await open;
    events.send(JSON.stringify({
      type: "response.create",
      response: {
        output_modalities: ["audio"],
        instructions: "Say exactly: Hello, welcome to your English practice.",
      },
    }));
    const [trackKind, doneEvent] = await Promise.all([remoteTrack, responseDone]);
    const deleted = await fetch(location, {
      method: "DELETE",
      headers: { "X-Termination-Reason": "user_finished" },
    });
    if (deleted.status !== 204) throw new Error(`delete_failed_${deleted.status}`);
    const metadata = await fetch(location).then((response) => response.json());
    peer.close();
    stream.getTracks().forEach((track) => track.stop());
    return {
      trackKind,
      doneEvent,
      status: metadata.status,
      sessionIdMatches: metadata.session_id === sessionId,
    };
  });
  if (
    result.trackKind !== "audio" ||
    result.doneEvent !== "response.done" ||
    result.status !== "ended" ||
    !result.sessionIdMatches
  ) {
    throw new Error(`Unexpected realtime result: ${JSON.stringify(result)}`);
  }
} finally {
  await browser.close();
}
