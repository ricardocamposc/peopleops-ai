"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const links = [["⌁", "Análisis", "/"], ["▣", "Policies", "/policies"], ["◈", "Human Review", "/human-review"]];
  return <main className="app-shell">
    <header className="topbar"><div className="brand-mark">P<span>·</span></div><div><p className="brand-name">PeopleOps <em>AI</em></p><p className="brand-subtitle">HR intelligence copilot</p></div><div className="topbar-spacer" /><span className="connection"><i /> API conectada</span></header>
    <div className="workspace"><aside className="sidebar"><div className="sidebar-label">ESPACIO DE TRABAJO</div>{links.map(([icon, label, href]) => <Link key={href} className={`nav-item ${pathname === href ? "nav-item--active" : ""}`} href={href}><span aria-hidden="true">{icon}</span><span>{label}</span></Link>)}<div className="sidebar-footer"><span className="eyebrow">ESTADO DEL SISTEMA</span><p>Datos y políticas con trazabilidad.</p></div></aside><div className="content">{children}</div></div>
  </main>;
}
