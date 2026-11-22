// S6.4 — WebSocket flood through nginx.
//
// Each VU is one seeded user (scripts/loadtest_seed.py) holding a socket on its
// room's channel. It sends a message every SEND_INTERVAL_S (jittered) and
// measures:
//   msg_rtt            send → own `message.new` echo (client clock only)
//   msg_fanout_latency server receive (`server_ts`) → delivery to the other
//                      sockets in the room. Same host clock in Docker, so valid
//                      locally; meaningless across machines.
//   msg_late           echo took longer than LATE_AFTER_MS (still timed in
//                      msg_rtt when it arrives)
//   msg_lost           no echo at all before the socket closed
//
// Run via `make load-test` (k6 on the compose network). Knobs (env):
//   VUS, RAMP, HOLD, SEND_INTERVAL_S, SESSION_S, WS_URL, TOKENS
import { SharedArray } from "k6/data";
import exec from "k6/execution";
import { WebSocket } from "k6/experimental/websockets";
import { Counter, Rate, Trend } from "k6/metrics";
import { clearInterval, setInterval, setTimeout } from "k6/timers";

const WS_URL = __ENV.WS_URL || "ws://nginx:8080";
const TOKENS = __ENV.TOKENS || "/scripts/.data/tokens.json";
const VUS = Number(__ENV.VUS || 100);
const RAMP = __ENV.RAMP || "1m";
const HOLD = __ENV.HOLD || "3m";
const SEND_INTERVAL_MS = Number(__ENV.SEND_INTERVAL_S || 5) * 1000;
// Each iteration is one socket session; the VU reconnects after it.
const SESSION_MS = Number(__ENV.SESSION_S || 120) * 1000;
// An echo slower than this counts as late (it is still timed when it arrives).
const LATE_AFTER_MS = 5000;
// At close, messages younger than this were cut off by our own close and are
// not counted as lost.
const CLOSE_GRACE_MS = 5000;

const users = new SharedArray("users", () => JSON.parse(open(TOKENS)));

const msgRtt = new Trend("msg_rtt", true);
const fanoutLatency = new Trend("msg_fanout_latency", true);
const msgSent = new Counter("msg_sent");
const msgEchoed = new Counter("msg_echoed");
const msgLate = new Counter("msg_late");
const msgLost = new Counter("msg_lost");
const msgReceived = new Counter("msg_received_others");
const serverErrors = new Counter("ws_server_errors");
const abnormalClose = new Counter("ws_abnormal_close");
const connectOk = new Rate("ws_connect_ok");

export const options = {
  scenarios: {
    flood: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: RAMP, target: VUS },
        { duration: HOLD, target: VUS },
        { duration: "20s", target: 0 },
      ],
      gracefulRampDown: "15s",
    },
  },
  thresholds: {
    ws_connecting: ["p(95)<500"],
    msg_rtt: ["p(99)<100"],
    ws_connect_ok: ["rate>0.99"],
    msg_lost: ["count<1"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max", "count"],
};

export function setup() {
  if (users.length < VUS) {
    // Two VUs as one user on one channel would replace each other's socket.
    exec.test.abort(`need >= ${VUS} seeded users, have ${users.length}`);
  }
}

export default function () {
  const me = users[(exec.vu.idInTest - 1) % users.length];
  const url = `${WS_URL}/ws/${me.channel_id}?token=${me.token}`;
  const pending = new Map(); // nonce -> sent at (ms)
  let seq = 0;
  let opened = false;
  let sender = null;

  const ws = new WebSocket(url);

  ws.onopen = () => {
    opened = true;
    connectOk.add(true);
    const send = () => {
      const nonce = `${exec.vu.idInTest}-${exec.vu.iterationInScenario}-${seq++}`;
      pending.set(nonce, Date.now());
      ws.send(JSON.stringify({ type: "message.new", payload: { content: `k6 ${nonce}` } }));
      msgSent.add(1);
    };
    // Spread first sends so VUs don't fire in lockstep.
    setTimeout(() => {
      send();
      sender = setInterval(send, SEND_INTERVAL_MS);
    }, Math.random() * SEND_INTERVAL_MS);
    setTimeout(() => ws.close(), SESSION_MS);
  };

  ws.onmessage = (e) => {
    const now = Date.now();
    const msg = JSON.parse(e.data);
    if (msg.type === "error") {
      serverErrors.add(1);
      return;
    }
    if (msg.type !== "message.new") return;
    const p = msg.payload;
    if (p.user_id === me.user_id) {
      const nonce = p.content.slice(3);
      const at = pending.get(nonce);
      if (at !== undefined) {
        msgRtt.add(now - at);
        msgEchoed.add(1);
        if (now - at > LATE_AFTER_MS) msgLate.add(1);
        pending.delete(nonce);
      }
    } else {
      msgReceived.add(1);
      fanoutLatency.add(now - p.server_ts);
    }
  };

  ws.onerror = () => {
    if (!opened) connectOk.add(false);
  };

  ws.onclose = (e) => {
    if (sender !== null) clearInterval(sender);
    if (!opened) connectOk.add(false);
    if (e && e.code && e.code !== 1000 && e.code !== 1005) abnormalClose.add(1);
    // Anything still unanswered after the grace window never came back;
    // younger messages were cut off by our own close and are not counted.
    const now = Date.now();
    for (const at of pending.values()) {
      if (now - at > CLOSE_GRACE_MS) msgLost.add(1);
    }
  };
}
