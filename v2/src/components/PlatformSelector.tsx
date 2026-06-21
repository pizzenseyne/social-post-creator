"use client";
import { PLATFORMS, type Platform } from "@/lib/types";
import clsx from "clsx";

interface Props {
  value: Platform;
  onChange: (p: Platform) => void;
}

export default function PlatformSelector({ value, onChange }: Props) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {PLATFORMS.map((p) => (
        <button
          key={p.id}
          onClick={() => onChange(p.id)}
          className={clsx(
            "flex flex-col items-center gap-2 px-3 py-4 rounded-2xl border-2 text-sm font-semibold transition-all duration-200",
            value === p.id
              ? "border-brand-500 bg-brand-50 text-brand-700 shadow-md shadow-brand-100"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50"
          )}
        >
          <span className="text-2xl">{p.icon}</span>
          <span>{p.name}</span>
          <span className="text-xs font-normal text-gray-400">{p.charLimit.toLocaleString()} car.</span>
        </button>
      ))}
    </div>
  );
}
