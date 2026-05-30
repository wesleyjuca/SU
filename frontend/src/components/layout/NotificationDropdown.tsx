"use client";
import { useRef, useEffect } from "react";
import Link from "next/link";
import { Bell, Check, CheckCheck, ExternalLink, X, Clock, FileText, CheckSquare, Bot } from "lucide-react";
import { useNotifications } from "@/hooks/useNotifications";
import { useNotificationStore } from "@/store";

const PRIORITY_COLORS: Record<string, string> = {
  URGENT: "border-l-red-500",
  HIGH: "border-l-orange-400",
  NORMAL: "border-l-afj-gold",
  LOW: "border-l-gray-300",
};

const TIPO_ICONS: Record<string, React.ReactNode> = {
  PRAZO_VENCENDO: <Clock size={13} className="text-amber-500 flex-shrink-0" />,
  NOVO_ANDAMENTO: <FileText size={13} className="text-blue-500 flex-shrink-0" />,
  APROVACAO_PENDENTE: <CheckSquare size={13} className="text-afj-gold flex-shrink-0" />,
  AGENTE_CONCLUIDO: <Bot size={13} className="text-purple-500 flex-shrink-0" />,
  SISTEMA: <Bell size={13} className="text-afj-black/40 flex-shrink-0" />,
};

interface NotificationDropdownProps {
  open: boolean;
  onClose: () => void;
}

export function NotificationDropdown({ open, onClose }: NotificationDropdownProps) {
  const { notifications } = useNotificationStore();
  const { markNotificationRead, markAllNotificationsRead } = useNotifications();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, onClose]);

  if (!open) return null;

  const unread = notifications.filter((n) => !n.lida);

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full mt-2 w-80 bg-white border border-afj-cream-dark rounded-xl shadow-lg z-50 overflow-hidden"
      style={{ maxHeight: "420px" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark bg-afj-cream/50">
        <div className="flex items-center gap-2">
          <Bell size={14} className="text-afj-black/60" />
          <span className="text-sm font-semibold text-afj-black">
            Notificações
            {unread.length > 0 && (
              <span className="ml-1.5 text-xs bg-red-500 text-white rounded-full px-1.5 py-0.5">
                {unread.length}
              </span>
            )}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {unread.length > 0 && (
            <button
              onClick={markAllNotificationsRead}
              className="text-xs text-afj-black/40 hover:text-afj-gold flex items-center gap-1"
              title="Marcar todas como lidas"
            >
              <CheckCheck size={12} />
              Todas
            </button>
          )}
          <button onClick={onClose} className="text-afj-black/30 hover:text-afj-black">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* List */}
      <div className="overflow-y-auto" style={{ maxHeight: "320px" }}>
        {notifications.length === 0 ? (
          <div className="py-8 text-center text-sm text-afj-black/40">
            Nenhuma notificação
          </div>
        ) : (
          notifications.map((notif) => (
            <div
              key={notif.id}
              className={`border-l-2 px-4 py-3 border-b border-afj-cream-dark last:border-b-0 transition-colors
                ${notif.lida ? "bg-white" : "bg-blue-50/40"}
                ${PRIORITY_COLORS[notif.priority] ?? "border-l-gray-300"}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    {TIPO_ICONS[notif.tipo ?? "SISTEMA"] ?? <Bell size={13} className="text-afj-black/40 flex-shrink-0" />}
                    <p className={`text-xs font-medium truncate ${notif.lida ? "text-afj-black/60" : "text-afj-black"}`}>
                      {notif.titulo}
                    </p>
                  </div>
                  {notif.corpo && (
                    <p className="text-xs text-afj-black/50 line-clamp-2">{notif.corpo}</p>
                  )}
                  <p className="text-xs text-afj-black/30 mt-1">
                    {new Date(notif.created_at).toLocaleString("pt-BR", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </p>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {notif.link && (
                    <Link
                      href={notif.link}
                      onClick={onClose}
                      className="text-afj-black/30 hover:text-afj-gold"
                    >
                      <ExternalLink size={11} />
                    </Link>
                  )}
                  {!notif.lida && (
                    <button
                      onClick={() => markNotificationRead(notif.id)}
                      className="text-afj-black/30 hover:text-green-600"
                      title="Marcar como lida"
                    >
                      <Check size={11} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-afj-cream-dark bg-afj-cream/30">
        <Link
          href="/aprovacoes"
          onClick={onClose}
          className="text-xs text-afj-gold hover:underline flex items-center gap-1"
        >
          Ver aprovações pendentes
          <ExternalLink size={10} />
        </Link>
      </div>
    </div>
  );
}

export function NotificationBell() {
  const { notifications } = useNotificationStore();
  const { unreadCount } = useNotifications();

  return (
    <>
      <Bell size={18} />
      {unreadCount > 0 && (
        <span className="absolute -top-1 -right-1 min-w-[14px] h-3.5 bg-red-500 rounded-full text-white text-[9px] flex items-center justify-center font-bold px-0.5">
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
    </>
  );
}
