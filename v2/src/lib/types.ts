export type Platform = "instagram" | "facebook" | "tiktok" | "linkedin" | "twitter";
export type Tone = "professionnel" | "fun" | "storytelling" | "inspirant" | "educatif";
export type Objectif = "vendre" | "informer" | "divertir" | "engager" | "evenement" | "inspirer";

export interface PostFormData {
  platform: Platform;
  tone: Tone;
  sujet: string;
  objectif: Objectif | "";
  cible: string;
  offre: string;
  cta: string;
  langue: string;
}

export interface GeneratedPost {
  caption: string;
  hashtags: string[];
  emojis: string[];
  tips: string[];
}

export const PLATFORMS: { id: Platform; name: string; color: string; charLimit: number; icon: string }[] = [
  { id: "instagram", name: "Instagram", color: "#E1306C", charLimit: 2200, icon: "📸" },
  { id: "facebook",  name: "Facebook",  color: "#1877F2", charLimit: 63000, icon: "👥" },
  { id: "tiktok",    name: "TikTok",    color: "#010101", charLimit: 150,   icon: "🎵" },
  { id: "linkedin",  name: "LinkedIn",  color: "#0A66C2", charLimit: 3000,  icon: "💼" },
  { id: "twitter",   name: "X / Twitter", color: "#1DA1F2", charLimit: 280, icon: "𝕏" },
];

export const TONES: { id: Tone; label: string; emoji: string; desc: string }[] = [
  { id: "professionnel", label: "Professionnel", emoji: "💼", desc: "Soigné et crédible" },
  { id: "fun",           label: "Fun",           emoji: "🎉", desc: "Léger et engageant" },
  { id: "storytelling",  label: "Storytelling",  emoji: "📖", desc: "Narratif et émotionnel" },
  { id: "inspirant",     label: "Inspirant",     emoji: "✨", desc: "Motivant et positif" },
  { id: "educatif",      label: "Éducatif",      emoji: "🎓", desc: "Instructif et clair" },
];

export const OBJECTIFS: { id: Objectif; label: string; emoji: string }[] = [
  { id: "vendre",    label: "Vendre",    emoji: "🛒" },
  { id: "informer",  label: "Informer",  emoji: "📢" },
  { id: "divertir",  label: "Divertir",  emoji: "😄" },
  { id: "engager",   label: "Engager",   emoji: "💬" },
  { id: "evenement", label: "Annoncer",  emoji: "📅" },
  { id: "inspirer",  label: "Inspirer",  emoji: "✨" },
];
