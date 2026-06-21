import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Social Post Creator — IA",
  description: "Créez des posts percutants pour vos réseaux sociaux avec l'IA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
