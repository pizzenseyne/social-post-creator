import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { PLATFORMS, TONES, OBJECTIFS, type PostFormData } from "@/lib/types";

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function POST(req: NextRequest) {
  try {
    const body: PostFormData = await req.json();
    const { platform, tone, sujet, objectif, cible, offre, cta, langue } = body;

    const platInfo = PLATFORMS.find((p) => p.id === platform);
    const toneInfo = TONES.find((t) => t.id === tone);
    const objInfo = OBJECTIFS.find((o) => o.id === objectif);

    const prompt = `Tu es un expert en marketing digital et rédaction de contenu pour les réseaux sociaux.

Crée un post ${platInfo?.name} optimisé avec ces informations :
- Sujet : ${sujet}
- Objectif : ${objInfo?.label || objectif}
- Cible : ${cible || "grand public"}
- Ton : ${toneInfo?.label || tone}
${offre ? `- Offre/Info clé : ${offre}` : ""}
${cta ? `- Appel à l'action : ${cta}` : ""}
- Langue : ${langue || "Français"}
- Limite de caractères : ${platInfo?.charLimit}

Réponds UNIQUEMENT avec un JSON valide dans ce format exact (sans markdown) :
{
  "caption": "Le texte principal du post (sans hashtags, respecte la limite de caractères)",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3"],
  "emojis": ["emoji1", "emoji2"],
  "tips": ["conseil1 pour maximiser l'engagement", "conseil2"]
}`;

    const message = await client.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 1024,
      messages: [{ role: "user", content: prompt }],
    });

    const content = message.content[0];
    if (content.type !== "text") throw new Error("Réponse invalide");

    const raw = content.text.trim().replace(/^```json?\n?/, "").replace(/\n?```$/, "");
    const parsed = JSON.parse(raw);

    return NextResponse.json(parsed);
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Erreur lors de la génération" }, { status: 500 });
  }
}
