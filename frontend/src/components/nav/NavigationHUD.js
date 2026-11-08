import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUp, ArrowUpLeft, ArrowUpRight, ChevronDown, ChevronUp, CornerUpLeft, CornerUpRight, Flag, Gauge, Loader2, Map as MapIcon, MessageCircle,
  Merge, Pause, Play, PictureInPicture2, RefreshCcw, RotateCcw, RotateCw, Ship, SkipForward, Volume2, VolumeX, WifiOff, X, Shuffle, CheckCircle2, PartyPopper,
} from "lucide-react";
import { fmtClock, fmtDist, fmtDur } from "@/lib/geo";

const ICONS = {
  TURN_LEFT: CornerUpLeft, TURN_SHARP_LEFT: CornerUpLeft, TURN_SLIGHT_LEFT: ArrowUpLeft,
  TURN_RIGHT: CornerUpRight, TURN_SHARP_RIGHT: CornerUpRight, TURN_SLIGHT_RIGHT: ArrowUpRight,
  UTURN_LEFT: RotateCcw, UTURN_RIGHT: RotateCw, RAMP_LEFT: ArrowUpLeft, RAMP_RIGHT: ArrowUpRight,
  FORK_LEFT: ArrowUpLeft, FORK_RIGHT: ArrowUpRight, MERGE: Merge, ROUNDABOUT_LEFT: RefreshCcw,
  ROUNDABOUT_RIGHT: RefreshCcw, FERRY: Ship, FERRY_TRAIN: Ship,
};

export const ManeuverIcon = ({ maneuver, className }) => {
  const I = ICONS[maneuver] || ArrowUp;
  return <I className={className} strokeWidth={2.6} />;
};

function Banner({ session }) {
  const { nav, phase, target, notice, gpsError } = session;
  let main, sub, icon = null, tone = "rf-banner";
  if (phase === "locating") { main = "Obtendo sua localização..."; sub = gpsError || "Permita o acesso ao GPS"; icon = <Loader2 className="h-9 w-9 animate-spin" />; }
  else if (phase === "routing") { main = "Calculando rota..."; sub = target?.label; icon = <Loader2 className="h-9 w-9 animate-spin" />; }
  else if (phase === "rerouting") { main = "Recalculando rota..."; sub = "Você saiu do trajeto"; icon = <Loader2 className="h-9 w-9 animate-spin" />; tone += " rf-banner-warn"; }
  else if (phase === "error") { main = "Não foi possível traçar a rota"; sub = notice; icon = <X className="h-9 w-9" />; tone += " rf-banner-err"; }
  else if (nav?.nextStep) {
    main = nav.nextStep.instruction;
    sub = fmtDist(nav.distToNext);
    icon = <ManeuverIcon maneuver={nav.nextStep.maneuver} className="h-10 w-10" />;
  } else if (nav) { main = `Chegando: ${target?.label || "destino"}`; sub = fmtDist(nav.remaining); icon = <Flag className="h-9 w-9" />; }
  else { main = "Preparando navegação..."; icon = <Loader2 className="h-9 w-9 animate-spin" />; }

  return (
    <motion.div initial={{ y: -120, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -120, opacity: 0 }}
      transition={{ type: "spring", damping: 24, stiffness: 260 }} className="pointer-events-auto">
      <div className={tone} data-testid="maneuver-banner">
        <div className="shrink-0">{icon}</div>
        <div className="min-w-0 flex-1">
          {sub && phase === "guiding" && nav?.nextStep && <p className="font-mono text-2xl sm:text-3xl font-bold leading-none" data-testid="maneuver-distance">{sub}</p>}
          <AnimatePresence mode="wait">
            <motion.p key={main} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className="text-base sm:text-lg font-extrabold tracking-tight leading-snug mt-1 line-clamp-2" data-testid="maneuver-instruction">{main}</motion.p>
          </AnimatePresence>
          {sub && !(phase === "guiding" && nav?.nextStep) && <p className="text-sm opacity-80 mt-0.5 truncate">{sub}</p>}
        </div>
      </div>
      {phase === "guiding" && nav?.thenStep && nav.distToNext < 400 && (
        <div className="rf-banner-then" data-testid="maneuver-then">
          Depois <ManeuverIcon maneuver={nav.thenStep.maneuver} className="h-4 w-4" />
        </div>
      )}
      {(notice || gpsError) && phase !== "error" && phase !== "locating" && (
        <div className="rf-banner-note" data-testid="nav-notice"><WifiOff className="h-3.5 w-3.5 shrink-0" />{notice || gpsError}</div>
      )}
    </motion.div>
  );
}

function BottomBar({ session, following, onOverview, onRecenter, onSendEta, onPip }) {
  const { nav, target, paused, gpsMode, simSpeed, setSimSpeed, voice, setVoice, remainingTargets } = session;
  const [collapsed, setCollapsed] = useState(false);
  const eta = nav ? fmtClock(new Date(Date.now() + nav.remainingS * 1000)) : "--:--";
  const hasNext = remainingTargets.findIndex((t) => t.key === target?.key) < remainingTargets.length - 1;
  return (
    <motion.div initial={{ y: 160, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 160, opacity: 0 }}
      transition={{ type: "spring", damping: 26, stiffness: 240 }} className="pointer-events-auto rf-navbar" data-testid="nav-bottom-bar">
      <button onClick={() => setCollapsed(!collapsed)} className="w-full flex justify-center -mt-1 mb-1 text-slate-400" aria-label={collapsed ? "Expandir" : "Recolher"} data-testid="nav-collapse-button">
        {collapsed ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
      </button>
      <div className="h-1 rounded-full bg-white/10 overflow-hidden mb-3">
        <motion.div className="h-full bg-emerald-400" animate={{ width: `${Math.round((nav?.progress || 0) * 100)}%` }} transition={{ ease: "linear" }} data-testid="nav-progress" />
      </div>
      <div className="flex items-center gap-3">
        <button onClick={session.stop} className="rf-round rf-round-danger" aria-label="Encerrar navegação" data-testid="stop-navigation-button"><X className="h-6 w-6" /></button>
        <div className="flex-1 min-w-0 text-center">
          <p className="font-mono text-2xl font-bold text-emerald-300 leading-none" data-testid="nav-remaining-time">{nav ? fmtDur(nav.remainingS) : "--"}</p>
          <p className="font-mono text-xs text-slate-300 mt-1" data-testid="nav-remaining-distance">{nav ? fmtDist(nav.remaining) : "--"} · chegada {eta}</p>
          <p className="text-[11px] text-slate-500 truncate mt-0.5" data-testid="nav-target-label">{target?.label}</p>
        </div>
        <button onClick={following ? onOverview : onRecenter} className="rf-round" aria-label={following ? "Visão geral" : "Recentralizar"} data-testid="nav-overview-button">
          {following ? <MapIcon className="h-5 w-5" /> : <ArrowUp className="h-5 w-5" />}
        </button>
      </div>
      {!collapsed && (
      <div className="flex items-center justify-center gap-2 mt-3 flex-wrap">
        <button onClick={session.togglePause} className="rf-pill" data-testid="pause-navigation-button">
          {paused ? <><Play className="h-4 w-4" />Retomar</> : <><Pause className="h-4 w-4" />Pausar</>}
        </button>
        {onSendEta && target?.key !== "base" && <button onClick={onSendEta} className="rf-pill" data-testid="nav-send-eta-button"><MessageCircle className="h-4 w-4" />Enviar previsão</button>}
        {onPip && <button onClick={onPip} className="rf-pill" data-testid="nav-pip-button"><PictureInPicture2 className="h-4 w-4" />Janela flutuante</button>}
        {hasNext && <button onClick={() => session.proceed(false)} className="rf-pill" data-testid="next-stop-button"><SkipForward className="h-4 w-4" />Próxima parada</button>}
        <button onClick={() => setVoice(!voice)} className="rf-pill" aria-label="Voz" data-testid="voice-toggle-button">
          {voice ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
        </button>
        {gpsMode === "sim" && (
          <>
            <button onClick={() => setSimSpeed(simSpeed >= 5 ? 1 : simSpeed === 1 ? 2 : 5)} className="rf-pill" data-testid="sim-speed-button"><Gauge className="h-4 w-4" />{simSpeed}x</button>
            <button onClick={session.deviate} className="rf-pill" data-testid="sim-deviate-button"><Shuffle className="h-4 w-4" />Simular desvio</button>
          </>
        )}
      </div>
      )}
    </motion.div>
  );
}

function ArrivalModal({ session }) {
  const { arrived, phase } = session;
  const finished = phase === "finished";
  if (!(phase === "arrived" && arrived) && !finished) return null;
  const isBase = arrived?.key === "base";
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="absolute inset-0 z-40 grid place-items-center bg-black/50 backdrop-blur-sm p-5 pointer-events-auto" data-testid="arrival-modal">
      <motion.div initial={{ scale: 0.85, y: 20 }} animate={{ scale: 1, y: 0 }} transition={{ type: "spring", damping: 18, stiffness: 240 }}
        className="w-full max-w-sm rf-glass-solid rounded-3xl p-6 text-center">
        <div className="relative mx-auto h-20 w-20">
          <span className="absolute inset-0 rounded-full bg-emerald-500/30 rf-pulse" />
          <span className="absolute inset-2 rounded-full bg-emerald-500 grid place-items-center">
            {finished ? <PartyPopper className="h-8 w-8 text-white" /> : <CheckCircle2 className="h-9 w-9 text-white" />}
          </span>
        </div>
        <p className="mt-5 text-2xl font-extrabold text-white tracking-tight">{finished ? "Roteiro finalizado" : "Você chegou"}</p>
        <p className="mt-1 text-sm text-slate-300">{finished ? "Todas as paradas foram percorridas." : arrived.label}</p>
        {!finished && <p className="text-xs text-slate-500 mt-1">{arrived.address}</p>}
        <div className="mt-6 grid gap-2">
          {finished ? (
            <button onClick={session.stop} className="rf-btn-go h-12 rounded-2xl" data-testid="finish-navigation-button">Voltar ao roteiro</button>
          ) : isBase ? (
            <button onClick={() => session.proceed(false)} className="rf-btn-go h-12 rounded-2xl" data-testid="arrival-confirm-button">Encerrar na base</button>
          ) : (
            <>
              <button onClick={() => session.proceed(true)} className="rf-btn-go h-12 rounded-2xl" data-testid="arrival-complete-button">Concluir parada e seguir</button>
              <button onClick={() => session.proceed(false)} className="rf-btn-ghost h-11 rounded-2xl text-sm" data-testid="arrival-skip-button">Seguir sem concluir</button>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

export function NavigationHUD({ session, following, onOverview, onRecenter, onSendEta, onPip }) {
  return (
    <div className="absolute inset-0 z-30 pointer-events-none flex flex-col justify-between p-3 sm:p-5" data-testid="navigation-hud">
      <div className="w-full sm:max-w-md rf-hud-top">
        <Banner session={session} />
        {session.phase === "error" && (
          <button onClick={session.retry} className="pointer-events-auto rf-pill mt-2" data-testid="nav-retry-button"><RefreshCcw className="h-4 w-4" />Tentar novamente</button>
        )}
      </div>
      <div className="w-full sm:max-w-md rf-hud-bottom">
        <BottomBar session={session} following={following} onOverview={onOverview} onRecenter={onRecenter} onSendEta={onSendEta} onPip={onPip} />
      </div>
      <AnimatePresence><ArrivalModal session={session} /></AnimatePresence>
    </div>
  );
}
