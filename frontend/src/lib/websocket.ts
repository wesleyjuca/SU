type EventHandler = (data: Record<string, unknown>) => void;

class AFJWebSocket {
  private ws: WebSocket | null = null;
  private userId: string | null = null;
  private handlers: Map<string, Set<EventHandler>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 2000;
  private maxReconnectDelay = 30000;
  private intentionallyClosed = false;

  connect(userId: string): void {
    this.userId = userId;
    this.intentionallyClosed = false;
    this._open();
  }

  disconnect(): void {
    this.intentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  on(eventType: string, handler: EventHandler): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);
    return () => this.handlers.get(eventType)?.delete(handler);
  }

  private _open(): void {
    if (!this.userId) return;
    const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
    if (!token) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/api/v1/ws/${this.userId}?token=${token}`;

    try {
      this.ws = new WebSocket(url);
    } catch {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectDelay = 2000;
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as Record<string, unknown>;
        const type = data.type as string;
        if (!type) return;

        // Dispatch to specific type handlers
        this.handlers.get(type)?.forEach((h) => h(data));
        // Dispatch to wildcard handlers
        this.handlers.get("*")?.forEach((h) => h(data));
      } catch {}
    };

    this.ws.onerror = () => {};

    this.ws.onclose = () => {
      this.ws = null;
      if (!this.intentionallyClosed) {
        this._scheduleReconnect();
      }
    };
  }

  private _scheduleReconnect(): void {
    if (this.intentionallyClosed) return;
    this.reconnectTimer = setTimeout(() => {
      this._open();
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
    }, this.reconnectDelay);
  }
}

// Singleton
export const afjWS = new AFJWebSocket();
export default afjWS;
