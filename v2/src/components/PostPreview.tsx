"use client";
import { PLATFORMS, type Platform, type GeneratedPost } from "@/lib/types";
import clsx from "clsx";

interface Props {
  platform: Platform;
  post: GeneratedPost;
  onCopy: () => void;
}

export default function PostPreview({ platform, post, onCopy }: Props) {
  const plat = PLATFORMS.find((p) => p.id === platform)!;
  const fullText = post.caption + (post.hashtags.length ? "\n\n" + post.hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ") : "");

  return (
    <div className="space-y-4">
      {/* Carte preview style réseau */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
        {/* Header */}
        <div className="flex items-center gap-3 p-4 border-b border-gray-100">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
            style={{ background: plat.color }}
          >
            {plat.icon}
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-900">Votre compte</div>
            <div className="text-xs text-gray-400">{plat.name} · À l'instant</div>
          </div>
        </div>

        {/* Corps */}
        <div className="p-4">
          <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{post.caption}</p>
          {post.hashtags.length > 0 && (
            <p className="mt-3 text-sm text-blue-500">
              {post.hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ")}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 pb-4 flex items-center gap-4 text-gray-400">
          <span className="text-xs">{post.caption.length} / {plat.charLimit.toLocaleString()} car.</span>
          <span
            className={clsx(
              "text-xs font-medium px-2 py-0.5 rounded-full",
              post.caption.length > plat.charLimit ? "bg-red-100 text-red-600" : "bg-green-100 text-green-600"
            )}
          >
            {post.caption.length > plat.charLimit ? "Trop long" : "OK"}
          </span>
        </div>
      </div>

      {/* Bouton copier */}
      <button
        onClick={onCopy}
        className="w-full py-3 rounded-2xl font-semibold text-white gradient-brand hover:opacity-90 transition-all flex items-center justify-center gap-2"
      >
        📋 Copier le post
      </button>

      {/* Tips IA */}
      {post.tips?.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 space-y-2">
          <div className="text-xs font-semibold text-amber-700 uppercase tracking-wide">Conseils IA</div>
          {post.tips.map((tip, i) => (
            <div key={i} className="flex gap-2 text-sm text-amber-800">
              <span className="text-amber-400 mt-0.5">•</span>
              {tip}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
