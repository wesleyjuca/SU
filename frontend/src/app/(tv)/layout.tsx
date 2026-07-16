// Route group do "Painel do Escritório" (modo quiosque para Smart TV):
// sem a sidebar/header do dashboard — tela cheia, fundo escuro, alto contraste.
export default function TvLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-afj-navy text-afj-cream">{children}</div>;
}
