import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ExternalLink } from "lucide-react";
import FrameworkTabs from "@/components/FrameworkTabs";

// ─── Resource cards ──────────────────────────────────────────────────────────

const resources = [
  {
    title: "Coding examples",
    description:
      "Worked decision-analysis examples in Julia, Python, and R — runnable notebooks with commentary.",
    href: "https://di4health.github.io/coding.html",
    badges: ["Julia", "Python", "R"],
  },
  {
    title: "Decision Analysis in R (DARTH)",
    description:
      "Open-source tutorials and packages for health-economic decision modeling from the DARTH workgroup.",
    href: "https://www.darthworkgroup.com/tutorials/",
    badges: ["R"],
  },
  {
    title: "TEAM Public Health",
    description:
      "Decision Intelligence for public health professionals — practice notes, frameworks, and case studies.",
    href: "https://teampublichealth.substack.com/p/decision-intelligence",
    badges: [],
  },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function HomePage() {
  return (
    <div className="max-w-4xl mx-auto space-y-16 py-8">

      {/* ── HERO ─────────────────────────────────────────────────────────── */}
      <section className="space-y-6">
        <Badge variant="secondary" className="text-xs tracking-wide uppercase">
          A project of TEAM Public Health
        </Badge>

        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Decision Intelligence 4 Health
        </h1>

        <p className="text-xl text-muted-foreground max-w-2xl">
          Better decisions are the highest-leverage skill in public health — yet
          decision quality is rarely taught. di4health is a practical framework
          and toolkit for making better decisions under real-world constraints.
        </p>

        {/* Annie Duke callout */}
        <blockquote className="border-l-4 border-primary pl-6 py-2 bg-card rounded-r-lg">
          <p className="text-base italic text-muted-foreground">
            &ldquo;There are only two things that determine how your life turns out:
            luck and the quality of your decisions. You have control over only
            one of those two things.&rdquo;
          </p>
          <footer className="mt-2 text-sm font-medium">
            — Annie Duke, <em>How to Decide</em>
          </footer>
        </blockquote>

        {/* CTAs */}
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/llm">Explore the decision tools</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="#framework">Learn the framework</Link>
          </Button>
        </div>
      </section>

      <Separator />

      {/* ── WHY DECISION QUALITY ─────────────────────────────────────────── */}
      <section className="space-y-6">
        <h2 className="text-2xl font-semibold tracking-tight">
          Why decision quality is hard
        </h2>

        <p className="text-muted-foreground leading-relaxed max-w-2xl">
          Decision making is our most important daily activity, but good
          decisions are hard for two reasons: <strong>organizational
          complexity</strong> and <strong>analytical complexity</strong>.
          di4health focuses on the analytical side — decision modeling
          (decision analysis) using modern data-science languages: Julia,
          Python, and R.
        </p>

        {/* Placeholder for competence-vs-complexity figure (E6) */}
        <div className="rounded-lg border border-dashed border-muted-foreground/40 bg-muted/30 flex items-center justify-center h-56 text-sm text-muted-foreground">
          [Figure: competence vs. complexity — re-hosted in E6]
        </div>
      </section>

      <Separator />

      {/* ── FRAMEWORK ANCHOR ─────────────────────────────────────────────── */}
      <section id="framework" className="space-y-6 scroll-mt-20">
        <h2 className="text-2xl font-semibold tracking-tight">
          The di4health framework
        </h2>

        <p className="text-muted-foreground leading-relaxed max-w-2xl">
          A holistic, practice-based framework for team decision making under
          real-world constraints, built on four pillars.
        </p>

        <FrameworkTabs />
      </section>

      <Separator />

      {/* ── RESOURCES ────────────────────────────────────────────────────── */}
      <section className="space-y-6">
        <h2 className="text-2xl font-semibold tracking-tight">Resources</h2>

        <div className="grid gap-4 sm:grid-cols-3">
          {resources.map((r) => (
            <Card key={r.title} className="flex flex-col">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{r.title}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col flex-1 gap-3">
                <p className="text-sm text-muted-foreground flex-1">
                  {r.description}
                </p>
                {r.badges.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {r.badges.map((b) => (
                      <Badge key={b} variant="outline" className="text-xs">
                        {b}
                      </Badge>
                    ))}
                  </div>
                )}
                <a
                  href={r.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-auto"
                >
                  Visit <ExternalLink className="h-3 w-3" />
                </a>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator />

      {/* ── FOOTER ───────────────────────────────────────────────────────── */}
      <footer className="space-y-2 pb-8">
        <p className="text-sm text-muted-foreground">
          di4health is a project of TEAM Public Health, created by Tomás
          Aragón. Content adapted from{" "}
          <a
            href="https://di4health.github.io"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-foreground"
          >
            di4health.github.io
          </a>
          .
        </p>
        <p className="text-xs text-muted-foreground/70">
          Annie Duke — <em>How to Decide</em> (2020); <em>Quit</em> (2023);{" "}
          <em>Thinking in Bets</em> (2020).
        </p>
      </footer>

    </div>
  );
}
