import Link from "next/link";
import { Fragment } from "react";
import { ChevronRight } from "lucide-react";

interface Crumb {
  label: string;
  href?: string;
}

export function Breadcrumb({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-afj-black/40 mb-4">
      {crumbs.map((c, i) => (
        <Fragment key={i}>
          {i > 0 && <ChevronRight size={11} className="flex-shrink-0" />}
          {c.href ? (
            <Link href={c.href} className="hover:text-afj-black transition-colors truncate max-w-[140px]">{c.label}</Link>
          ) : (
            <span className="text-afj-black/70 font-medium truncate max-w-[200px]">{c.label}</span>
          )}
        </Fragment>
      ))}
    </nav>
  );
}
