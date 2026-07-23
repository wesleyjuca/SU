"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useVoice (Bloco F / F6) — conversa por voz do assistente do Cérebro.
 *
 * Baseado 100% na Web Speech API do navegador (sem backend, sem custo):
 * - STT: SpeechRecognition (webkit) — reconhecimento contínuo pt-BR.
 * - TTS: speechSynthesis — fala as respostas do assistente.
 *
 * Recursos exigidos pelo plano:
 * - Conversa contínua: ao terminar de falar a resposta, reabre o microfone.
 * - Barge-in: se o usuário começar a falar enquanto o assistente fala, o TTS
 *   é imediatamente cancelado (interrupção).
 * - Baixa latência: tudo client-side; parciais em tempo real (interim results).
 * - Fallback: `supported=false` quando o navegador não tem as APIs → a UI
 *   continua funcionando por texto.
 */

// Tipagem mínima da Web Speech API (não faz parte do lib.dom padrão).
interface SpeechRecognitionAlternative { transcript: string; confidence: number }
interface SpeechRecognitionResult { readonly length: number; isFinal: boolean;[i: number]: SpeechRecognitionAlternative }
interface SpeechRecognitionResultList { readonly length: number;[i: number]: SpeechRecognitionResult }
interface SpeechRecognitionEventLike { resultIndex: number; results: SpeechRecognitionResultList }
interface SpeechRecognitionErrorEventLike { error: string }
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export interface UseVoiceOptions {
  /** Chamado quando o usuário conclui uma fala (transcrição final). */
  onFinal: (texto: string) => void;
  /** Idioma do reconhecimento/síntese (default pt-BR). */
  lang?: string;
}

export interface UseVoiceApi {
  supported: boolean;
  /** Modo voz ativado pelo usuário (loop contínuo de escuta). */
  active: boolean;
  /** Microfone captando neste instante. */
  listening: boolean;
  /** Assistente falando (TTS) neste instante. */
  speaking: boolean;
  /** Transcrição parcial (interim) para feedback visual. */
  interim: string;
  /** Liga/desliga o modo de conversa por voz. */
  toggle: () => void;
  /** Encerra o modo voz e cala qualquer fala. */
  stop: () => void;
  /** Fala um texto (resposta do assistente). Reabre o mic ao terminar se ativo. */
  speak: (texto: string) => void;
  /** Cala imediatamente o TTS (usado no barge-in e ao desmontar). */
  shutUp: () => void;
}

export function useVoice({ onFinal, lang = "pt-BR" }: UseVoiceOptions): UseVoiceApi {
  const [supported] = useState(() => getRecognitionCtor() !== null && ttsSupported());
  const [active, setActive] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [interim, setInterim] = useState("");

  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const activeRef = useRef(false);       // espelho síncrono de `active` p/ callbacks
  const speakingRef = useRef(false);     // espelho síncrono de `speaking`
  const onFinalRef = useRef(onFinal);
  useEffect(() => { onFinalRef.current = onFinal; }, [onFinal]);

  // ─── TTS ───────────────────────────────────────────────────────────────────
  const shutUp = useCallback(() => {
    if (!ttsSupported()) return;
    try { window.speechSynthesis.cancel(); } catch { /* noop */ }
    speakingRef.current = false;
    setSpeaking(false);
  }, []);

  // ─── STT ───────────────────────────────────────────────────────────────────
  const startListening = useCallback(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor || recRef.current) return;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => setListening(true);

    rec.onresult = (e) => {
      let parcial = "";
      let finalTxt = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const txt = r[0]?.transcript ?? "";
        if (r.isFinal) finalTxt += txt;
        else parcial += txt;
      }
      // Barge-in: usuário voltou a falar enquanto o assistente falava → corta TTS.
      if ((parcial || finalTxt) && speakingRef.current) shutUp();
      setInterim(parcial);
      const limpo = finalTxt.trim();
      if (limpo) {
        setInterim("");
        onFinalRef.current(limpo);
      }
    };

    rec.onerror = (ev) => {
      // "no-speech"/"aborted" são recuperáveis; o onend cuida do reinício.
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        activeRef.current = false;
        setActive(false);
      }
    };

    rec.onend = () => {
      setListening(false);
      recRef.current = null;
      // Loop contínuo: enquanto o modo voz estiver ligado e o assistente não
      // estiver falando, reabre o microfone (baixa latência).
      if (activeRef.current && !speakingRef.current) {
        // reinício imediato; try/catch p/ corridas do engine
        try { startListening(); } catch { /* noop */ }
      }
    };

    recRef.current = rec;
    try { rec.start(); } catch { recRef.current = null; }
  }, [lang, shutUp]);

  const stopListening = useCallback(() => {
    const rec = recRef.current;
    recRef.current = null;
    if (rec) { try { rec.abort(); } catch { /* noop */ } }
    setListening(false);
    setInterim("");
  }, []);

  const speak = useCallback((texto: string) => {
    const limpo = (texto || "").trim();
    if (!ttsSupported() || !limpo) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(limpo);
      u.lang = lang;
      u.rate = 1.05;
      u.onstart = () => { speakingRef.current = true; setSpeaking(true); };
      u.onend = () => {
        speakingRef.current = false;
        setSpeaking(false);
        // Terminou de falar → reabre o mic se ainda em modo voz.
        if (activeRef.current) startListening();
      };
      u.onerror = () => {
        speakingRef.current = false;
        setSpeaking(false);
        if (activeRef.current) startListening();
      };
      // Enquanto fala, pausa a escuta p/ não captar a própria voz (eco).
      stopListening();
      window.speechSynthesis.speak(u);
    } catch { /* noop */ }
  }, [lang, startListening, stopListening]);

  // ─── Controle do modo voz ────────────────────────────────────────────────────
  const stop = useCallback(() => {
    activeRef.current = false;
    setActive(false);
    stopListening();
    shutUp();
  }, [stopListening, shutUp]);

  const toggle = useCallback(() => {
    if (activeRef.current) { stop(); return; }
    if (!supported) return;
    activeRef.current = true;
    setActive(true);
    startListening();
  }, [supported, stop, startListening]);

  // Limpeza ao desmontar.
  useEffect(() => () => {
    activeRef.current = false;
    try { recRef.current?.abort(); } catch { /* noop */ }
    recRef.current = null;
    if (ttsSupported()) { try { window.speechSynthesis.cancel(); } catch { /* noop */ } }
  }, []);

  return { supported, active, listening, speaking, interim, toggle, stop, speak, shutUp };
}
