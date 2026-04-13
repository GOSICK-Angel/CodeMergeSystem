import WebSocket from "ws";
import { useAppStore } from "./store.js";

interface WSCallbacks {
  onOpen?: () => void;
  onClose?: () => void;
}

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

const THROTTLE_MS = 200;
let pendingSnapshot: Record<string, unknown> | null = null;
let throttleTimer: ReturnType<typeof setTimeout> | null = null;

function flushPendingSnapshot() {
  if (pendingSnapshot) {
    const data = pendingSnapshot;
    pendingSnapshot = null;
    useAppStore.getState().applySnapshot(data);
  }
  throttleTimer = null;
}

export function connectWS(url: string, callbacks: WSCallbacks): () => void {
  const store = useAppStore.getState;

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return;

    ws = new WebSocket(url);

    ws.on("open", () => {
      callbacks.onOpen?.();
    });

    ws.on("message", (raw: WebSocket.Data) => {
      try {
        const msg = JSON.parse(raw.toString());
        handleMessage(msg);
      } catch {
        // ignore unparseable messages
      }
    });

    ws.on("close", () => {
      callbacks.onClose?.();
      scheduleReconnect();
    });

    ws.on("error", () => {
      // error events are followed by close
    });
  }

  function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      store().setConnectionStatus("connecting");
      connect();
    }, 3000);
  }

  function handleMessage(msg: { type: string; payload?: unknown }) {
    const { applyPatch, setAgentActivity } = useAppStore.getState();
    switch (msg.type) {
      case "state_snapshot":
      case "state_patch":
        pendingSnapshot = msg.payload as Record<string, unknown>;
        if (!throttleTimer) {
          throttleTimer = setTimeout(flushPendingSnapshot, THROTTLE_MS);
        }
        break;
      case "agent_activity":
        setAgentActivity(msg.payload as { agent: string; action: string });
        break;
      case "phase_started":
        applyPatch({
          currentPhase: (msg.payload as { phase: string }).phase as never,
        });
        break;
      default:
        break;
    }
  }

  connect();

  return () => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (throttleTimer) clearTimeout(throttleTimer);
    if (ws) {
      ws.removeAllListeners();
      ws.close();
      ws = null;
    }
  };
}

export function sendCommand(command: { type: string; payload?: unknown }) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(command));
  }
}
