import "./globals.css";
export const metadata = {
  title: "Axiom | Research workspace",
  description: "Reproducible quantitative research and paper execution",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
