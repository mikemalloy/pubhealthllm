"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dices,
  Scale,
  Siren,
  ListChecks,
  Database,
  Heart,
  Clock,
  Wallet,
  CheckCircle2,
  Map,
  RefreshCcw,
  FlaskConical,
  Brain,
  Lightbulb,
  BarChart2,
  Layers,
} from "lucide-react";

// ── Tab 1: DEEP Challenges ───────────────────────────────────────────────────

const deepCards = [
  {
    letter: "D",
    icon: Dices,
    title: "Decision making under uncertainty",
    badge: "Information",
    blurb: "Choosing when data, knowledge, and the future are incomplete.",
  },
  {
    letter: "E",
    icon: Scale,
    title: "Ethical decision making",
    badge: "Values",
    blurb: "Weighing moral trade-offs so benefits outweigh risks.",
  },
  {
    letter: "E",
    icon: Siren,
    title: "Emergency & crisis decision making",
    badge: "Time",
    blurb: "High-stakes choices under severe time pressure.",
  },
  {
    letter: "P",
    icon: ListChecks,
    title: "Priority setting & resource allocation",
    badge: "Resources",
    blurb: "Investment trade-offs across competing needs.",
  },
];

// ── Tab 2: Constraints ───────────────────────────────────────────────────────

const constraintCards = [
  {
    icon: Database,
    title: "Information",
    blurb: "Data, knowledge, and an uncertain future.",
  },
  {
    icon: Heart,
    title: "Values",
    blurb: "Moral trade-offs between competing goods.",
  },
  {
    icon: Clock,
    title: "Time",
    blurb: "Speed vs. deliberation under pressure.",
  },
  {
    icon: Wallet,
    title: "Resources",
    blurb: "Limited budget, people, and capacity.",
  },
];

// ── Tab 3: Dimensions ────────────────────────────────────────────────────────

const dimensionCards = [
  {
    icon: CheckCircle2,
    title: "Decision quality",
    blurb: "Making the best possible choice given available information.",
  },
  {
    icon: Map,
    title: "Strategy execution",
    blurb: "Operating within frameworks: ICS, lean, PDSA/A3, RBA.",
  },
  {
    icon: RefreshCcw,
    title: "Continuous improvement",
    blurb: "Learning loops that raise decision quality over time.",
  },
  {
    icon: FlaskConical,
    title: "Ethics, science & technology",
    blurb: "Grounding decisions in evidence, values, and emerging tools.",
  },
];

// ── Tab 4: Competencies ──────────────────────────────────────────────────────

const competencyCards = [
  {
    icon: Brain,
    title: "Recognizing & resisting cognitive biases",
    blurb: "Identifying the mental shortcuts that distort judgment.",
  },
  {
    icon: Lightbulb,
    title: "Valuing & applying rationality",
    blurb: "Choosing beliefs and actions that align with goals and evidence.",
  },
  {
    icon: BarChart2,
    title: "Thinking probabilistically",
    blurb: "Reasoning about uncertainty with calibrated confidence.",
  },
  {
    icon: Layers,
    title: "Structuring decisions",
    blurb: "Framing problems to separate decisions from outcomes.",
  },
];

// ── Shared card components ───────────────────────────────────────────────────

function DeepCard({
  letter,
  icon: Icon,
  title,
  badge,
  blurb,
}: (typeof deepCards)[number]) {
  return (
    <Card className="flex flex-col gap-0 overflow-hidden">
      <CardHeader className="pb-3">
        {/* Large typographic letter accent */}
        <div className="flex items-start justify-between gap-2">
          <span className="text-7xl font-black leading-none text-primary/20 select-none">
            {letter}
          </span>
          <Icon className="h-6 w-6 mt-2 text-primary shrink-0" />
        </div>
        <h3 className="text-base font-semibold leading-snug">{title}</h3>
        <Badge variant="secondary" className="w-fit text-xs">
          {badge}
        </Badge>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{blurb}</p>
      </CardContent>
    </Card>
  );
}

function SimpleCard({
  icon: Icon,
  title,
  blurb,
}: {
  icon: React.ElementType;
  title: string;
  blurb: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">{title}</h3>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{blurb}</p>
      </CardContent>
    </Card>
  );
}

// ── FrameworkTabs ────────────────────────────────────────────────────────────

export default function FrameworkTabs() {
  return (
    <Tabs defaultValue="deep">
      <TabsList className="mb-4 flex flex-wrap h-auto gap-1">
        <TabsTrigger value="deep">DEEP Challenges</TabsTrigger>
        <TabsTrigger value="constraints">Constraints</TabsTrigger>
        <TabsTrigger value="dimensions">Dimensions</TabsTrigger>
        <TabsTrigger value="competencies">Competencies</TabsTrigger>
      </TabsList>

      {/* ── Tab 1: DEEP Challenges ── */}
      <TabsContent value="deep">
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {deepCards.map((c) => (
            <DeepCard key={c.letter + c.title} {...c} />
          ))}
        </div>
      </TabsContent>

      {/* ── Tab 2: Constraints ── */}
      <TabsContent value="constraints">
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {constraintCards.map((c) => (
            <SimpleCard key={c.title} {...c} />
          ))}
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          These constraints often occur simultaneously in DEEP decisions.
        </p>
      </TabsContent>

      {/* ── Tab 3: Dimensions ── */}
      <TabsContent value="dimensions">
        <p className="mb-4 text-sm text-muted-foreground">
          Strategic decisions occur within execution frameworks (ICS, lean,
          PDSA/A3, Results-Based Accountability).
        </p>
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {dimensionCards.map((c) => (
            <SimpleCard key={c.title} {...c} />
          ))}
        </div>
      </TabsContent>

      {/* ── Tab 4: Competencies ── */}
      <TabsContent value="competencies">
        <p className="mb-4 text-sm text-muted-foreground">
          Core decision competencies from the Alliance for Decision Education.
        </p>
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {competencyCards.map((c) => (
            <SimpleCard key={c.title} {...c} />
          ))}
        </div>
      </TabsContent>
    </Tabs>
  );
}
