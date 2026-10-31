import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "SAF Supply Chain Report: Kalimantan",
  description: "Biomass depots, SAF refineries and truck routes to Kalimantan's four international airports.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        {/* Font Awesome 6.2.0: the plane and factory icons the Streamlit map (folium) uses. */}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css" />
      </head>
      <body className={`${inter.variable} font-sans`}>{children}</body>
    </html>
  );
}
