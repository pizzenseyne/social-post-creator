"use client";
import { useState, useCallback } from "react";
import PlatformSelector from "@/components/PlatformSelector";
import ToneSelector from "@/components/ToneSelector";
import PostPreview from "@/components/PostPreview";
import { OBJECTIFS, type Platform, type Tone, type Objectif, type GeneratedPost } from "@/lib/types";
import clsx from "clsx";

type Step = "form" | "result";

const LANGUES = ["Français", "Anglais", "Espagnol", "Arabe", "Portugais", "Allemand"];

export default function Home() {
  const [step, setStep] = useState<Step>("form");
  const [platform, setPlatform] = useState<Platform>("instagram");
  const [tone, setTone] = useState<Tone>("professionnel");
  const [objectif, setObjectif] = useState<Objectif | "">("");
  const [sujet, setSujet] = useState("");
  const [cible, setCible] = useState("");
  const [offre, setOffre] = useState("");
  const [cta, setCta] = useState("");
  const [langue, setLangue] = useState("Français");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<GeneratedPost | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = useCallback(async () => {
    if (!sujet.trim()) { setError("Décrivez d'abord votre sujet."); return; }
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, tone, sujet, objectif, cible, offre, cta, langue }),
      });
      if (!res.ok) throw new Error((await res.json()).error || "Erreur serveur");
      const data: GeneratedPost = await res.json();
      setResult(data);
      setStep("result");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [platform, tone, sujet, objectif, cible, offre, cta, langue]);

  const handleCopy = () => {
    if (!result) return;
    const text = result.caption + (result.hashtags.length ? "\n\n" + result.hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ") : "");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-brand-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white/70 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl gradient-brand flex items-center justify-center text-white font-bold text-lg">S</div>
            <div>
              <div className="font-bold text-gray-900 leading-tight">Social Post Creator</div>
              <div className="text-xs text-gray-400">Propulsé par Claude AI</div>
            </div>
          </div>
          {step === "result" && (
            <button onClick={() => { setStep("form"); setResult(null); }} className="text-sm text-brand-600 font-medium hover:underline">
              ← Nouveau post
            </button>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        {step === "form" && (
          <div className="space-y-10">
            {/* Hero */}
            <div className="text-center">
              <h1 className="text-4xl font-extrabold text-gray-900 mb-3">
                Créez des posts qui{" "}
                <span className="text-transparent bg-clip-text gradient-brand">engagent</span>
              </h1>
              <p className="text-lg text-gray-500 max-w-xl mx-auto">
                Remplissez le formulaire, l'IA génère une légende percutante adaptée à votre réseau.
              </p>
            </div>

            {/* Plateforme */}
            <section>
              <h2 className="text-base font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full gradient-brand text-white text-xs flex items-center justify-center font-bold">1</span>
                Choisissez votre réseau
              </h2>
              <PlatformSelector value={platform} onChange={setPlatform} />
            </section>

            {/* Sujet */}
            <section>
              <h2 className="text-base font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full gradient-brand text-white text-xs flex items-center justify-center font-bold">2</span>
                Décrivez votre contenu
              </h2>
              <textarea
                value={sujet}
                onChange={(e) => setSujet(e.target.value)}
                rows={3}
                placeholder="Ex: Notre nouveau produit cosmétique bio, photos du lancement en boutique, promotion -30% ce weekend..."
                className="w-full border border-gray-300 rounded-2xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none bg-white shadow-sm"
              />
            </section>

            {/* Objectif */}
            <section>
              <h2 className="text-base font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full gradient-brand text-white text-xs flex items-center justify-center font-bold">3</span>
                Objectif du post
              </h2>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
                {OBJECTIFS.map((o) => (
                  <button
                    key={o.id}
                    onClick={() => setObjectif(objectif === o.id ? "" : o.id)}
                    className={clsx(
                      "flex flex-col items-center gap-2 py-3 rounded-2xl border-2 text-xs font-semibold transition-all",
                      objectif === o.id
                        ? "border-brand-500 bg-brand-50 text-brand-700"
                        : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
                    )}
                  >
                    <span className="text-xl">{o.emoji}</span>
                    {o.label}
                  </button>
                ))}
              </div>
            </section>

            {/* Ton */}
            <section>
              <h2 className="text-base font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full gradient-brand text-white text-xs flex items-center justify-center font-bold">4</span>
                Ton de la légende
              </h2>
              <ToneSelector value={tone} onChange={setTone} />
            </section>

            {/* Champs optionnels */}
            <section>
              <h2 className="text-base font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full gradient-brand text-white text-xs flex items-center justify-center font-bold">5</span>
                Détails supplémentaires{" "}
                <span className="text-gray-400 font-normal text-sm">(optionnel)</span>
              </h2>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wide">Audience cible</label>
                  <input
                    value={cible}
                    onChange={(e) => setCible(e.target.value)}
                    placeholder="Ex: femmes 25-40 ans, passionnées de bien-être"
                    className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wide">Offre ou info clé</label>
                  <input
                    value={offre}
                    onChange={(e) => setOffre(e.target.value)}
                    placeholder="Ex: -30% ce weekend, livraison offerte..."
                    className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wide">Appel à l'action</label>
                  <input
                    value={cta}
                    onChange={(e) => setCta(e.target.value)}
                    placeholder="Ex: Lien en bio, Réservez maintenant..."
                    className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wide">Langue</label>
                  <select
                    value={langue}
                    onChange={(e) => setLangue(e.target.value)}
                    className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white"
                  >
                    {LANGUES.map((l) => <option key={l}>{l}</option>)}
                  </select>
                </div>
              </div>
            </section>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">{error}</div>
            )}

            <button
              onClick={handleGenerate}
              disabled={loading || !sujet.trim()}
              className="w-full py-4 rounded-2xl font-bold text-white text-base gradient-brand hover:opacity-90 transition-all flex items-center justify-center gap-3 disabled:opacity-50 shadow-lg shadow-brand-200"
            >
              {loading ? (
                <>
                  <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Génération en cours...
                </>
              ) : (
                <>✨ Générer mon post avec l'IA</>
              )}
            </button>
          </div>
        )}

        {step === "result" && result && (
          <div className="max-w-2xl mx-auto space-y-8">
            <div className="text-center">
              <div className="text-4xl mb-3">🎉</div>
              <h2 className="text-2xl font-bold text-gray-900 mb-1">Votre post est prêt !</h2>
              <p className="text-gray-500 text-sm">Copiez-le et publiez-le directement sur votre réseau.</p>
            </div>

            <PostPreview platform={platform} post={result} onCopy={handleCopy} />

            {copied && (
              <div className="fixed bottom-6 right-6 bg-green-600 text-white px-5 py-3 rounded-xl shadow-lg text-sm font-medium z-50">
                ✓ Copié dans le presse-papiers !
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => { setStep("form"); setResult(null); }}
                className="flex-1 py-3 rounded-2xl border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 transition-all"
              >
                ← Modifier les paramètres
              </button>
              <button
                onClick={handleGenerate}
                disabled={loading}
                className="flex-1 py-3 rounded-2xl gradient-brand text-white font-semibold hover:opacity-90 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {loading ? "..." : "↺ Régénérer"}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
