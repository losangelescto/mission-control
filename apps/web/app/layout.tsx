import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import { JetBrains_Mono } from "next/font/google";
import { NavMenu } from "./components/NavMenu";
import SearchBar from "./components/SearchBar";
import { ThemeToggle } from "./components/ThemeToggle";
import "./globals.css";

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
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
    <html lang="en" className={jetBrainsMono.variable} suppressHydrationWarning>
      <body>
        {/*
          Blocking script injected into <head> via beforeInteractive.
          Adds the `dark` class before first paint — zero flash of wrong theme.
          Light is the default; only add dark when user has explicitly saved "dark".
        */}
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('mc-theme');if(t==='dark')document.documentElement.classList.add('dark');}catch(e){}`,
          }}
        />

        <header className="topbar">
          <div className="topbar-inner">
            <Link href="/" className="brand">
              <span className="brand-mark">▸</span>
              MISSION CONTROL
            </Link>
            <NavMenu />
            <SearchBar />
            <ThemeToggle />
          </div>
        </header>

        <main className="page-container">{children}</main>
      </body>
    </html>
  );
}
