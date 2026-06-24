import { useLoaderData } from "react-router-dom";
import { Seo } from "../seo/Seo";
import { weaponJsonLd } from "../seo/jsonld";

interface Perk {
  name: string;
  description: string;
  rating?: string;
}

interface Stat {
  name: string;
  value: number;
}

interface Weapon {
  slug: string;
  name: string;
  type: string;
  element: string;
  ammoType: string;
  frame: string;
  stats: Stat[];
  perks: Perk[];
  godRoll: string[];
}

export async function loader({ params }: { params: { slug?: string } }) {
  const slug = params.slug;
  if (!slug) return null;
  try {
    // Dynamic import resolves the JSON at build time via Vite's module graph.
    // This works in both SSG (server) and client-side navigation.
    const mod = await import(`../content/weapons/${slug}.json`);
    return mod.default as Weapon;
  } catch {
    return null;
  }
}

export function Component() {
  const weapon = useLoaderData() as Weapon | null;

  if (!weapon) {
    return (
      <main className="p-8 max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold mb-4">Weapon not found</h1>
        <p>The weapon you are looking for does not exist or has not been indexed yet.</p>
      </main>
    );
  }

  const hasPerks = weapon.perks && weapon.perks.length > 0;
  const hasGodRoll = weapon.godRoll && weapon.godRoll.length > 0;

  return (
    <>
      <Seo
        title={`${weapon.name} god roll & perks — Destiny Advisor`}
        description={`Best perks, god roll, and stats for ${weapon.name} (${weapon.type}, ${weapon.element}). Find out which perk combinations maximize your damage output.`}
        path={`/weapons/${weapon.slug}`}
        jsonLd={weaponJsonLd(weapon)}
      />
      <main className="p-8 max-w-3xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">{weapon.name}</h1>
        <p className="text-gray-500 mb-6">
          {weapon.type} &middot; {weapon.element}
          {weapon.ammoType ? ` · ${weapon.ammoType} Ammo` : ""}
        </p>

        {weapon.stats && weapon.stats.length > 0 && (
          <section className="mb-8">
            <h2 className="text-xl font-semibold mb-3">Stats</h2>
            <ul className="space-y-1">
              {weapon.stats.map((stat) => (
                <li key={stat.name} className="flex justify-between max-w-sm">
                  <span className="text-gray-700">{stat.name}</span>
                  <span className="font-mono font-medium">{stat.value}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {hasPerks ? (
          <section className="mb-8">
            <h2 className="text-xl font-semibold mb-3">Perks</h2>
            <ul className="space-y-2">
              {weapon.perks.map((perk) => (
                <li key={perk.name} className="border rounded p-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{perk.name}</span>
                    {perk.rating && (
                      <span className="text-sm font-bold text-blue-600">
                        [{perk.rating}]
                      </span>
                    )}
                  </div>
                  {perk.description && (
                    <p className="text-sm text-gray-600 mt-1">{perk.description}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <section className="mb-8">
            <h2 className="text-xl font-semibold mb-3">Perks</h2>
            <p className="text-gray-500 italic">Perk data coming soon.</p>
          </section>
        )}

        {hasGodRoll && (
          <section className="mb-8">
            <h2 className="text-xl font-semibold mb-3">Recommended God Roll</h2>
            <ul className="list-disc list-inside space-y-1">
              {weapon.godRoll.map((perkName) => (
                <li key={perkName} className="text-green-700 font-medium">
                  {perkName}
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </>
  );
}

export default Component;
