import type { Metadata } from "next";
import { Source_Sans_3 } from "next/font/google";
import "./globals.css";

// Streamlit's own UI font, so the app reads like the Streamlit dashboard.
const sourceSans = Source_Sans_3({ subsets: ["latin"], variable: "--font-source-sans" });

export const metadata: Metadata = {
  title: "Kalimantan SAF Planner",
  description: "Biomass depots, SAF refineries and truck routes to Kalimantan's four international airports.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        {/* Font Awesome 6.2.0: the plane and factory icons the Streamlit map (folium) uses. */}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css" />
      </head>
      <body className={`${sourceSans.variable} font-sans`}>{children}</body>
    </html>
  );
}
