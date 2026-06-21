"use client";
import { TONES, type Tone } from "@/lib/types";
import clsx from "clsx";

interface Props {
  value: Tone;
  onChange: (t: Tone) => void;
}

export default function ToneSelector({ value, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {TONES.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          title={t.desc}
          className={clsx(
            "flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium border-2 transition-all duration-200",
            value === t.id
              ? "border-brand-500 bg-brand-500 text-white shadow-sm"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
          )}
        >
          <span>{t.emoji}</span>
          {t.label}
        </button>
      ))}
    </div>
  );
}
