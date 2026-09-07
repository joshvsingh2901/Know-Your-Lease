import { IBM_Plex_Mono, IBM_Plex_Sans, Instrument_Serif, Newsreader } from "next/font/google";

export const fontSerifDisplay = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-serif-display",
  display: "swap",
});

export const fontSerifText = Newsreader({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-serif-text",
  display: "swap",
});

export const fontSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans-editorial",
  display: "swap",
});

export const fontMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono-editorial",
  display: "swap",
});

export const landingFontVariables = `${fontSerifDisplay.variable} ${fontSerifText.variable} ${fontSans.variable} ${fontMono.variable}`;
