import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Staytus · Your next chapter, clearly",
  description: "A personal status and policy navigator for international students and scholars.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
