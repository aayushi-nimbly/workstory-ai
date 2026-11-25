"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

interface NavLinkProps {
  href: string;
  icon: string;
  children: React.ReactNode;
  trailing?: React.ReactNode;
}

function Item({ href, icon, children, trailing, active }: NavLinkProps & { active: boolean }) {
  return (
    <Link href={href} className={`nav-item${active ? " active" : ""}`}>
      <span className="nav-icon">{icon}</span>
      {children}
      {trailing}
    </Link>
  );
}

function ActiveItem(props: NavLinkProps) {
  const pathname = usePathname();
  const active = pathname === props.href || pathname.startsWith(`${props.href}/`);
  return <Item {...props} active={active} />;
}

/** Sidebar link. The current URL is runtime data, so highlighting streams in under Suspense. */
export function NavLink(props: NavLinkProps) {
  return (
    <Suspense fallback={<Item {...props} active={false} />}>
      <ActiveItem {...props} />
    </Suspense>
  );
}
