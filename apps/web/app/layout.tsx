import type { Metadata } from "next";
import Script from "next/script";
import { JetBrains_Mono, Newsreader } from "next/font/google";
import { AppShell } from "./components/AppShell";
import "./globals.css";

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
});

const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  display: "swap",
  weight: ["300", "400", "500", "600"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Mission Control",
  description: "Mission Control — operational task management",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-theme="light"
      className={`${jetBrainsMono.variable} ${newsreader.variable}`}
      suppressHydrationWarning
    >
      <body>
        {/*
          Blocking script injected via beforeInteractive. Reads the saved theme
          from localStorage and sets data-theme on <html> before first paint, so
          the cascade picks the right token block and there's no FOUC.
        */}
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('mc.theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}`,
          }}
        />

        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
