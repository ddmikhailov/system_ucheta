import { describe, expect, it } from "vitest";
import indexHtml from "../../index.html?raw";
import manifestRaw from "../../public/manifest.webmanifest?raw";

// «На экран Домой»: манифест подключён в index.html, а все его значки лежат в public/.
const publicFiles = Object.keys(import.meta.glob("../../public/*.png", { query: "?url", eager: true })).map((p) =>
  p.replace("../../public", ""),
);

describe("манифест приложения", () => {
  const manifest = JSON.parse(manifestRaw) as { display: string; start_url: string; icons: { src: string; sizes: string }[] };

  it("открывается как приложение и подключён в index.html", () => {
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/");
    expect(indexHtml).toContain('<link rel="manifest" href="/manifest.webmanifest" />');
  });

  it("значки 192 и 512 px лежат в public/", () => {
    expect(manifest.icons.map((i) => i.sizes)).toEqual(expect.arrayContaining(["192x192", "512x512"]));
    for (const icon of manifest.icons) expect(publicFiles).toContain(icon.src);
  });
});
