import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function TeamPage() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-10 space-y-12">

      {/* ── INTRO ─────────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Team</h1>
        <p className="text-lg text-muted-foreground leading-relaxed max-w-2xl">
          Decision Intelligence 4 Health is a collaborative project to improve
          the real-time decision making of public health agencies, and other
          health and human services organizations.
        </p>
      </section>

      <Separator />

      {/* ── LEAD ──────────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Lead</h2>
        <Card className="bg-card border">
          <CardContent className="pt-6">
            <p className="font-medium text-foreground">
              <a
                href="https://substack.com/@tomasaragon"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                Tomás Aragón
              </a>
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              <a
                href="https://teampublichealth.substack.com/"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-foreground"
              >
                TEAM Public Health
              </a>{" "}
              and UC Berkeley Public Health
            </p>
          </CardContent>
        </Card>
      </section>

      <Separator />

      {/* ── COLLABORATORS / CONTRIBUTORS ──────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">
          Collaborators &amp; Contributors
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            { name: "Gilda Zarate-Gonzalez", affiliation: "Decision Intelligence Section, CDPH" },
            { name: "Hector Manuel Sanchez Castellanos", affiliation: "Decision Intelligence Section, CDPH" },
            { name: "Lauren White", affiliation: "Decision Intelligence Section, CDPH" },
            { name: "Lisa Bandong", affiliation: "Office of Planning & Planning, CDPH" },
            { name: "Natalie Linton", affiliation: "Decision Intelligence Section, CDPH" },
            { name: "Phoebe Lu", affiliation: "Decision Intelligence Section, CDPH" },
            { name: "Tomás León", affiliation: "Decision Intelligence Section, CDPH" },
          ].map((person) => (
            <Card key={person.name} className="bg-card border">
              <CardContent className="pt-5 pb-5">
                <p className="font-medium text-foreground">{person.name}</p>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {person.affiliation}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator />

      {/* ── ACKNOWLEDGMENTS ───────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Acknowledgments</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Card className="bg-card border">
            <CardContent className="pt-5 pb-5">
              <p className="font-medium text-foreground">
                <a
                  href="https://www.annieduke.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Annie Duke
                </a>
              </p>
              <p className="text-sm text-muted-foreground mt-0.5">
                author, speaker, and consultant
              </p>
            </CardContent>
          </Card>
          <Card className="bg-card border">
            <CardContent className="pt-5 pb-5">
              <p className="font-medium text-foreground">
                <a
                  href="https://med.stanford.edu/profiles/douglas-owens"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Doug Owens
                </a>
              </p>
              <p className="text-sm text-muted-foreground mt-0.5">
                Stanford University
              </p>
            </CardContent>
          </Card>
          <Card className="bg-card border">
            <CardContent className="pt-5 pb-5">
              <p className="font-medium text-foreground">
                <a
                  href="https://healthpolicy.fsi.stanford.edu/people/joshua-salomon"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Joshua Salomon
                </a>
              </p>
              <p className="text-sm text-muted-foreground mt-0.5">
                Stanford University
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      <Separator />

      {/* ── FOOTNOTES ─────────────────────────────────────────────────────── */}
      <footer className="space-y-1 pb-8">
        <p className="text-xs text-muted-foreground">
          1. CDPH = California Department of Public Health.
        </p>
        <p className="text-xs text-muted-foreground">
          2. Sox, Harold C., Michael C. Higgins, Douglas K. Owens, and Gillian
          Sanders Schmidler.{" "}
          <em>Medical Decision Making.</em> 3rd ed. John Wiley &amp; Sons, 2024.
        </p>
      </footer>

    </main>
  );
}
