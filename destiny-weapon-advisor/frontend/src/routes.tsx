import type { RouteRecord } from "vite-react-ssg";
import React from "react";
import { PublicLayout } from "./components/PublicLayout";

export const routes: RouteRecord[] = [
  {
    path: "/",
    element: <PublicLayout />,
    entry: "src/components/PublicLayout.tsx",
    children: [
      {
        index: true,
        Component: React.lazy(() => import("./pages/Landing")),
      },
      {
        path: "weapons/:slug",
        lazy: () => import("./pages/WeaponPage"),
        getStaticPaths: async () => {
          const index = (await import("./content/weapons-index.json")).default as Array<{ slug: string }>;
          return index.map((w) => `weapons/${w.slug}`);
        },
      },
    ],
  },
  {
    path: "/app/*",
    lazy: () =>
      import("./components/AppShell").then((m) => ({ Component: m.AppShell })),
  },
];
