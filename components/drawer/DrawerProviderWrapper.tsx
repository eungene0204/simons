"use client";

import { DrawerProvider } from "@/contexts/DrawerContext";

export default function DrawerProviderWrapper({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DrawerProvider>{children}</DrawerProvider>;
}

