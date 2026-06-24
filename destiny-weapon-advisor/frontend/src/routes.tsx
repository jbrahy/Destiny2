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
    ],
  },
  {
    path: "/app/*",
    lazy: () =>
      import("./components/AppShell").then((m) => ({ Component: m.AppShell })),
  },
];
