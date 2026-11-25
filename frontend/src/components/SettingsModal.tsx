import React, { useEffect, useState } from 'react';
import {
  X,
  Save,
  Volume2,
  Cpu,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Download,
  Key,
} from 'lucide-react';
import { api } from '../api/client';
import { useStudioStore } from '../store/studioStore';
import type { ElevenLabsVoice, Settings } from '../types';

export const SettingsModal: React.FC = () => {
  const {
    settingsModalOpen,
    setSettingsModalOpen,
    settings,
    models,
    saveSettings,
    showToast,
    refreshAssetLibrary,
  } = useStudioStore();

  const [form, setForm] = useState<Settings | null>(null);
  const [voices, setVoices] = useState<ElevenLabsVoice[]>([]);
  const [voicesNote, setVoicesNote] = useState<string | null>(null);
  const [ttsModels, setTtsModels] = useState<{ model_id: string; name: string }[]>([]);
  const [customVoiceId, setCustomVoiceId] = useState('');
  const [checkingVoice, setCheckingVoice] = useState(false);
  const [loadingVoices, setLoadingVoices] = useState(false);
  const [previewingVoice, setPreviewingVoice] = useState(false);
  const [detectingBlender, setDetectingBlender] = useState(false);
  const [syncingBK, setSyncingBK] = useState(false);
  const [bkSyncResult, setBkSyncResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    if (settingsModalOpen && settings) {
      setForm({ ...settings });
      setBkSyncResult(null);
      setLoadingVoices(true);
      api
        .listVoices()
        .then((res) => {
          setVoices(res.voices);
          setVoicesNote(res.source === 'live' ? `${res.voices.length} voices on your account` : res.error);
        })
        .catch(() => {})
        .finally(() => setLoadingVoices(false));
      api.ttsModels().then((r) => setTtsModels(r.models)).catch(() => {});
      setCustomVoiceId('');
    }
  }, [settingsModalOpen, settings]);

  const handleCheckVoice = async () => {
    if (!customVoiceId.trim()) return;
    setCheckingVoice(true);
    try {
      if (form?.elevenlabs_api_key) await api.saveSettings(form);
      const res = await api.checkVoice(customVoiceId);
      setVoices((vs) => (vs.some((v) => v.voice_id === res.voice.voice_id) ? vs : [res.voice, ...vs]));
      setForm((f) => (f ? { ...f, elevenlabs_voice_id: res.voice.voice_id, elevenlabs_voice_name: res.voice.name } : f));
      showToast('success', `Voice found: ${res.voice.name} (${res.voice.category}). Selected.`);
    } catch (e: any) {
      showToast('error', e.message);
    } finally {
      setCheckingVoice(false);
    }
  };

  if (!settingsModalOpen || !form) return null;

  const setField = <K extends keyof Settings>(k: K, v: Settings[K]) => {
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev));
  };

  const handleSave = async () => {
    await saveSettings(form);
    setSettingsModalOpen(false);
  };

  const handleDetectBlender = async () => {
    setDetectingBlender(true);
    try {
      const res = await api.detectBlender();
      if (res.blender_found && res.blender_path) {
        setField('blender_path', res.blender_path);
        showToast('success', `Detected Blender ${res.blender_version} at ${res.blender_path}`);
      } else {
        showToast('error', res.error || 'Could not auto-detect Blender.');
      }
    } catch (e: any) {
      showToast('error', e.message);
    } finally {
      setDetectingBlender(false);
    }
  };

  const handleSyncBlenderKit = async () => {
    setSyncingBK(true);
    setBkSyncResult(null);
    try {
      const res = await api.installBlenderKit({
        source_path: form.blenderkit_source_path,
        blender_path: form.blender_path,
        api_key: form.blenderkit_api_key,
      });
      setBkSyncResult({ ok: res.ok, message: res.message });
      await refreshAssetLibrary();
      showToast(res.ok ? 'success' : 'error', res.message);
    } catch (e: any) {
      setBkSyncResult({ ok: false, message: e.message });
      showToast('error', e.message);
    } finally {
      setSyncingBK(false);
    }
  };

  const handlePreviewVoice = async () => {
    if (!form.elevenlabs_api_key) {
      showToast('error', 'Enter and save your ElevenLabs API key first to preview live voices.');
      return;
    }
    setPreviewingVoice(true);
    try {
      await api.saveSettings(form);
      const blob = await api.previewVoice(form.elevenlabs_voice_id);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play();
      audio.onended = () => URL.revokeObjectURL(url);
    } catch (e: any) {
      showToast('error', e.message);
    } finally {
      setPreviewingVoice(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl max-h-[90vh] bg-card border border-borderStrong rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-borderSubtle flex items-center justify-between bg-sidebar">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold text-ink">Stick Knowledge 3D Studio — Settings</h2>
          </div>
          <button
            onClick={() => setSettingsModalOpen(false)}
            className="p-1 rounded-lg text-inkMuted hover:text-ink hover:bg-card"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
          {/* Anthropic Claude */}
          <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-accent">
              Anthropic Claude AI Director (Prompt Caching Enabled)
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-inkMuted mb-1">Anthropic API Key</label>
                <input
                  type="password"
                  value={form.anthropic_api_key}
                  onChange={(e) => setField('anthropic_api_key', e.target.value)}
                  placeholder="sk-ant-api03-..."
                  className="w-full bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink font-mono focus:outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="block text-inkMuted mb-1">Claude Model</label>
                <select
                  value={form.claude_model}
                  onChange={(e) => setField('claude_model', e.target.value)}
                  className="w-full bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink focus:outline-none focus:border-accent"
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-inkMuted mb-1">API Budget Limit (USD Tracker)</label>
              <input
                type="number"
                min={5}
                step={5}
                value={form.budget_limit_usd}
                onChange={(e) => setField('budget_limit_usd', Number(e.target.value) || 100)}
                className="w-36 bg-card border border-borderStrong rounded-lg px-3 py-1.5 text-ink font-mono focus:outline-none focus:border-accent"
              />
            </div>
          </div>

          {/* ElevenLabs */}
          <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-violet-400">
              ElevenLabs Narration & Word-Level Timestamps
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-inkMuted mb-1">ElevenLabs API Key</label>
                <input
                  type="password"
                  value={form.elevenlabs_api_key}
                  onChange={(e) => setField('elevenlabs_api_key', e.target.value)}
                  placeholder="sk_..."
                  className="w-full bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink font-mono focus:outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="block text-inkMuted mb-1">Narrator Voice</label>
                <div className="flex gap-1.5">
                  <select
                    value={form.elevenlabs_voice_id}
                    onChange={(e) => {
                      const v = voices.find((x) => x.voice_id === e.target.value);
                      setField('elevenlabs_voice_id', e.target.value);
                      if (v) setField('elevenlabs_voice_name', v.name);
                    }}
                    className="flex-1 min-w-0 bg-card border border-borderStrong rounded-lg px-2.5 py-2 text-ink focus:outline-none focus:border-accent"
                  >
                    {!voices.some((v) => v.voice_id === form.elevenlabs_voice_id) && (
                      <option value={form.elevenlabs_voice_id}>{form.elevenlabs_voice_name || form.elevenlabs_voice_id}</option>
                    )}
                    {Array.from(new Set(voices.map((v) => v.category || 'other'))).map((cat) => (
                      <optgroup key={cat} label={cat === 'premade' ? 'Premade' : cat === 'cloned' ? 'My cloned voices' : cat === 'professional' ? 'Professional / Voice Library' : cat === 'generated' ? 'Voice Design (generated)' : cat}>
                        {voices
                          .filter((v) => (v.category || 'other') === cat)
                          .map((v) => (
                            <option key={v.voice_id} value={v.voice_id}>
                              {v.name}
                            </option>
                          ))}
                      </optgroup>
                    ))}
                  </select>
                  <button
                    onClick={handlePreviewVoice}
                    disabled={previewingVoice || loadingVoices}
                    title="Preview Voice"
                    className="px-3 py-2 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-ink flex items-center gap-1 shrink-0"
                  >
                    {previewingVoice ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Volume2 className="w-3.5 h-3.5 text-violet-400" />
                    )}
                    Preview
                  </button>
                </div>
                {voicesNote && <div className="mt-1 text-[11px] text-inkDim">{voicesNote}</div>}
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-inkMuted mb-1">Custom Voice ID (any voice you can use on ElevenLabs)</label>
                <div className="flex gap-1.5">
                  <input
                    value={customVoiceId}
                    onChange={(e) => setCustomVoiceId(e.target.value)}
                    placeholder="Paste a Voice ID, e.g. 21m00Tcm4TlvDq8ikWAM"
                    className="flex-1 min-w-0 bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink font-mono focus:outline-none focus:border-accent"
                  />
                  <button
                    onClick={handleCheckVoice}
                    disabled={!customVoiceId.trim() || checkingVoice}
                    className="px-3 py-2 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-ink shrink-0 disabled:opacity-50"
                  >
                    {checkingVoice ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Use'}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-inkMuted mb-1">Voice Model</label>
                <select
                  value={form.elevenlabs_model_id || 'eleven_multilingual_v2'}
                  onChange={(e) => setField('elevenlabs_model_id', e.target.value)}
                  className="w-full bg-card border border-borderStrong rounded-lg px-2.5 py-2 text-ink focus:outline-none focus:border-accent"
                >
                  {(ttsModels.length ? ttsModels : [{ model_id: form.elevenlabs_model_id || 'eleven_multilingual_v2', name: form.elevenlabs_model_id || 'eleven_multilingual_v2' }]).map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.name} ({m.model_id})
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="p-3 rounded-lg bg-card border border-borderSubtle text-[11px] text-inkMuted leading-relaxed">
              <span className="text-ink font-medium">Own voiceover instead?</span> Use “Upload voiceover” in the chat header
              (or drop an .mp3/.wav/.m4a into the chat). It's word-timed locally with faster-whisper and the storyboard
              locks to it — no ElevenLabs credits needed.
              <div className="mt-2 flex items-center gap-2">
                <span>Transcription model:</span>
                <select
                  value={form.whisper_model || 'small.en'}
                  onChange={(e) => setField('whisper_model', e.target.value)}
                  className="bg-canvas border border-borderStrong rounded px-2 py-1 text-ink"
                >
                  <option value="base.en">base.en (fastest, English)</option>
                  <option value="small.en">small.en (recommended, English)</option>
                  <option value="medium.en">medium.en (most accurate, English, slower)</option>
                  <option value="small">small (multilingual)</option>
                  <option value="medium">medium (multilingual, slower)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Blender & BlenderKit */}
          <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-studioCyan">
              Blender Engine & Pre-Extracted BlenderKit Add-on
            </h3>

            <div>
              <label className="block text-inkMuted mb-1">Blender Executable Path</label>
              <div className="flex gap-2">
                <input
                  value={form.blender_path}
                  onChange={(e) => setField('blender_path', e.target.value)}
                  placeholder="D:\B Software LK\blender.exe"
                  className="flex-1 bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink font-mono focus:outline-none focus:border-accent"
                />
                <button
                  onClick={handleDetectBlender}
                  disabled={detectingBlender}
                  className="px-3 py-2 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-ink flex items-center gap-1.5 shrink-0"
                >
                  {detectingBlender ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5 text-studioCyan" />
                  )}
                  Auto-Detect
                </button>
              </div>
            </div>

            <div>
              <label className="block text-inkMuted mb-1">BlenderKit Add-on Source Path</label>
              <div className="flex gap-2">
                <input
                  value={form.blenderkit_source_path}
                  onChange={(e) => setField('blenderkit_source_path', e.target.value)}
                  className="flex-1 bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink font-mono focus:outline-none focus:border-accent"
                />
                <button
                  onClick={handleSyncBlenderKit}
                  disabled={syncingBK}
                  className="px-3 py-2 rounded-lg bg-studioCyan/20 hover:bg-studioCyan/30 border border-studioCyan/40 text-studioCyan font-medium flex items-center gap-1.5 shrink-0"
                >
                  {syncingBK ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Download className="w-3.5 h-3.5" />
                  )}
                  Install/Sync BlenderKit into Blender
                </button>
              </div>
              {bkSyncResult && (
                <div
                  className={`mt-2 px-3 py-2 rounded-lg border text-[11px] flex items-start gap-2 ${
                    bkSyncResult.ok
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                      : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                  }`}
                >
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>{bkSyncResult.message}</span>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-inkMuted mb-1">
                  BlenderKit Free API Key <span className="text-inkDim">(Optional)</span>
                </label>
                <input
                  type="password"
                  value={form.blenderkit_api_key}
                  onChange={(e) => setField('blenderkit_api_key', e.target.value)}
                  placeholder="Optional free BlenderKit token"
                  className="w-full bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink font-mono focus:outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="block text-inkMuted mb-1">
                  Hugging Face Token <span className="text-inkDim">(Optional Free AI 3D)</span>
                </label>
                <input
                  type="password"
                  value={form.huggingface_token}
                  onChange={(e) => setField('huggingface_token', e.target.value)}
                  placeholder="hf_... (avoids Space rate limits)"
                  className="w-full bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink font-mono focus:outline-none focus:border-accent"
                />
              </div>
            </div>
          </div>

          {/* Render Engine Toggle */}
          <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5" /> Render Engine & GPU Optimization
            </h3>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => setField('render_engine', 'EEVEE_NEXT')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  form.render_engine === 'EEVEE_NEXT'
                    ? 'bg-accent/15 border-accent text-ink'
                    : 'bg-card border-borderSubtle text-inkMuted hover:border-borderStrong'
                }`}
              >
                <div className="font-semibold text-xs">EEVEE Next (Fast)</div>
                <div className="text-[11px] text-inkDim mt-0.5">
                  Raytraced real-time rasterizer · Ideal for instant previews & rapid Shorts
                </div>
              </button>
              <button
                type="button"
                onClick={() => setField('render_engine', 'CYCLES_OPTIX')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  form.render_engine === 'CYCLES_OPTIX'
                    ? 'bg-accent/15 border-accent text-ink'
                    : 'bg-card border-borderSubtle text-inkMuted hover:border-borderStrong'
                }`}
              >
                <div className="font-semibold text-xs">Cycles GPU OptiX (Cinematic)</div>
                <div className="text-[11px] text-inkDim mt-0.5">
                  OptiX + OpenImageDenoise · Memory-safe 6GB+ VRAM · True SSS & glass
                </div>
              </button>
            </div>

            {form.render_engine === 'CYCLES_OPTIX' && (
              <div className="flex items-center justify-between pt-1">
                <label className="text-inkMuted">Cycles Samples (64–96 recommended):</label>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={32}
                    max={128}
                    step={8}
                    value={form.cycles_samples}
                    onChange={(e) => setField('cycles_samples', Number(e.target.value))}
                    className="accent-[#D97757]"
                  />
                  <span className="font-mono text-ink w-10 text-right">{form.cycles_samples}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3.5 border-t border-borderSubtle bg-sidebar flex items-center justify-end gap-2">
          <button
            onClick={() => setSettingsModalOpen(false)}
            className="px-4 py-2 rounded-lg bg-card hover:bg-cardHover text-xs text-inkMuted"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 rounded-lg bg-accent hover:bg-accentHover text-white text-xs font-medium flex items-center gap-1.5"
          >
            <Save className="w-3.5 h-3.5" />
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};
