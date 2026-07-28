import { chromium } from "playwright";

const baseUrl = process.env.PEDAGOGICAL_E2E_BASE_URL ?? "http://127.0.0.1:8000";
const fixturePath = process.env.PEDAGOGICAL_E2E_AUDIO_FIXTURE;
if (!fixturePath) throw new Error("PEDAGOGICAL_E2E_AUDIO_FIXTURE is required");

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
    const requestJson = async (path, options = {}) => {
      const response = await fetch(path, options);
      if (!response.ok) throw new Error(`${path}_failed_${response.status}`);
      return { response, payload: await response.json() };
    };
    const missions = await fetch("/v1/missions").then((response) => response.json());
    if (!Array.isArray(missions) || missions.length === 0) throw new Error("no_missions");
    const installationId = "github-actions-pedagogy-e2e";
    const createdMission = await requestJson("/v1/mission-sessions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Installation-Id": installationId,
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        mission_id: missions[0].id,
        processing_consent: true,
        content_retention_consent: false,
      }),
    });
    const mission = createdMission.payload;
    const token = createdMission.response.headers.get("X-Mission-Session-Token");
    if (!token) throw new Error("missing_mission_token");
    const authorization = { Authorization: `Bearer ${token}` };
    const peer = new RTCPeerConnection();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => peer.addTrack(track, stream));
    const events = peer.createDataChannel("oai-events");
    let completedTranscripts = 0;
    let remoteAudio = false;
    events.onmessage = ({ data }) => {
      const event = JSON.parse(data);
      if (event.type === "conversation.item.input_audio_transcription.completed") {
        completedTranscripts += 1;
      }
      if (event.type === "error") throw new Error("provider_event_error");
    };
    peer.ontrack = ({ track }) => {
      if (track.kind === "audio") remoteAudio = true;
    };
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
    const createdCall = await fetch("/v1/realtime/calls", {
      method: "POST",
      headers: {
        "Content-Type": "application/sdp",
        "X-Installation-Id": installationId,
        "Idempotency-Key": crypto.randomUUID(),
        "X-Mission-Session-Id": mission.session_id,
        ...authorization,
      },
      body: peer.localDescription.sdp,
    });
    if (createdCall.status !== 201) {
      throw new Error(`create_call_failed_${createdCall.status}`);
    }
    const callLocation = createdCall.headers.get("Location");
    if (!callLocation) throw new Error("missing_call_location");
    await peer.setRemoteDescription({ type: "answer", sdp: await createdCall.text() });

    const submitted = new Set();
    const waitingKinds = {
      FIRST_ATTEMPT_WAITING: "first",
      RETRY_WAITING: "retry",
      TRANSFER_WAITING: "transfer",
    };
    const deadline = Date.now() + 180_000;
    let canonical = mission;
    try {
      while (Date.now() < deadline) {
        canonical = (
          await requestJson(`/v1/mission-sessions/${mission.session_id}`, {
            headers: authorization,
          })
        ).payload;
        if (canonical.state === "MISSION_COMPLETED") break;
        const kind = waitingKinds[canonical.state];
        if (
          kind &&
          !submitted.has(kind) &&
          completedTranscripts > submitted.size
        ) {
          const completedAt = new Date().toISOString();
          const startedAt = new Date(Date.now() - 4_000).toISOString();
          await requestJson(`/v1/mission-sessions/${mission.session_id}/attempts`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Idempotency-Key": crypto.randomUUID(),
              ...authorization,
            },
            body: JSON.stringify({
              client_attempt_id: crypto.randomUUID(),
              state_version: canonical.state_version,
              kind,
              help_level: "NO_HELP",
              started_at: startedAt,
              completed_at: completedAt,
              used_time_extension: false,
            }),
          });
          submitted.add(kind);
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      if (canonical.state !== "MISSION_COMPLETED") {
        throw new Error(`mission_timeout_${canonical.state}`);
      }
      const summary = await requestJson(
        `/v1/mission-sessions/${mission.session_id}/summary`,
        { headers: authorization },
      );
      if (summary.payload.textual_content_available !== false) {
        throw new Error("unexpected_text_retention");
      }
      if (!remoteAudio) throw new Error("remote_audio_missing");
      if (submitted.size !== 3) throw new Error(`attempt_count_${submitted.size}`);
    } finally {
      await fetch(callLocation, {
        method: "DELETE",
        headers: { "X-Termination-Reason": "user_finished" },
      });
      peer.close();
      stream.getTracks().forEach((track) => track.stop());
    }
    return {
      missionState: canonical.state,
      attempts: submitted.size,
      remoteAudio,
    };
  });
  if (
    result.missionState !== "MISSION_COMPLETED" ||
    result.attempts !== 3 ||
    !result.remoteAudio
  ) {
    throw new Error(`Unexpected pedagogical result: ${JSON.stringify(result)}`);
  }
} finally {
  await browser.close();
}
