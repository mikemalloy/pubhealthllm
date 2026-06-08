import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function CodingPage() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-10 space-y-12">

      {/* ── INTRO ─────────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">
          Decision modeling – Jupyter notebooks
        </h1>
        <Card className="bg-card border">
          <CardContent className="pt-6 pb-6 space-y-4">
            <p className="text-muted-foreground leading-relaxed">
              The purpose of this site is to develop a Jupyter notebook repository of health
              economic decision modeling (aka, decision analysis) coding examples to support
              analysts who are learning how to code to solve practical decision problems. A
              secondary purpose is to have a repository for training artificial intelligence to
              assist us in tackling more complex decision problems.
            </p>
            <div className="space-y-2">
              <p className="text-foreground leading-relaxed">
                For decision modeling we will be focusing on the following approaches:
              </p>
              <ul className="list-disc list-inside space-y-1 text-foreground">
                <li>decision trees</li>
                <li>influence diagrams (Bayesian decision networks)</li>
                <li>agent-based modeling</li>
              </ul>
            </div>
            <div className="space-y-2">
              <p className="text-muted-foreground leading-relaxed">
                The following open source software packages are used for decision modeling and
                leverage different approaches: decision trees, Bayesian networks (e.g., influence
                diagrams), mixed-integer linear programming (MILP) (i.e., optimization), and
                agent-based modeling.
              </p>
              <ol className="list-decimal list-inside space-y-1 text-foreground">
                <li>
                  R:{" "}
                  <a
                    href="https://cran.r-project.org/web/packages/rdecision/index.html"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline hover:text-primary"
                  >
                    rdecision
                  </a>
                  : for decision trees
                </li>
                <li>
                  Python:{" "}
                  <a
                    href="https://pyagrum.gitlab.io/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline hover:text-primary"
                  >
                    pyAgrum
                  </a>
                  : for influence diagrams with Bayesian networks
                </li>
                <li>
                  Julia:{" "}
                  <a
                    href="https://gamma-opt.github.io/DecisionProgramming.jl/dev/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline hover:text-primary"
                  >
                    DecisionProgramming.jl
                  </a>
                  : for influence diagrams with MILP
                </li>
                <li>
                  Julia:{" "}
                  <a
                    href="https://juliadynamics.github.io/Agents.jl/stable/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline hover:text-primary"
                  >
                    Agents.jl
                  </a>
                  : for agent-based modeling
                </li>
              </ol>
            </div>
            <p className="text-muted-foreground leading-relaxed">
              We are early in our journey and invite critical feedback, input, and suggestions.
            </p>
            <p className="text-foreground leading-relaxed">
              Do you want to contribute a Jupyter notebook? Contact{" "}
              <a
                href="http://substack.com/@tomasaragon"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                Tomás Aragón
              </a>
              .
            </p>
          </CardContent>
        </Card>
      </section>

      <Separator />

      {/* ── SPECIAL ANNOUNCEMENTS ─────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Special announcements</h2>
        <Card className="bg-card border">
          <CardContent className="pt-6 pb-6 space-y-4">
            <h3 className="text-base font-semibold text-foreground">
              Building a decision tree model in R (tutorial)
            </h3>
            <p className="text-muted-foreground leading-relaxed">
              From Mirko von Hein, learn how to build a healthcare decision tree model in R from
              scratch to calculate ICERs, run one-way sensitivity analyses, and create tornado
              diagrams for cost-effectiveness analysis.
            </p>
            {/* Responsive 16:9 YouTube embed */}
            <div className="w-full aspect-video rounded-lg overflow-hidden">
              <iframe
                src="https://www.youtube.com/embed/8fvr0NaUKE8"
                title="How to Build a Decision Tree Model in R"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="w-full h-full"
              />
            </div>
            <p className="text-foreground leading-relaxed">
              Here is the{" "}
              <a
                href="https://github.com/MvonHein/Decision-Tree-Model-in-R/blob/main/decision_tree_tut_R.R"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                R code
              </a>{" "}
              for this YouTube tutorial (Feb 15, 2026).
            </p>
          </CardContent>
        </Card>
      </section>

      <Separator />

      {/* ── DECISION MODELS ───────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Decision models</h2>

        {/* Petitti 2000 */}
        <Card className="bg-card border">
          <CardContent className="pt-6 pb-6 space-y-4">
            <h3 className="text-base font-semibold text-foreground">
              Decision Analysis (Chapter 2, Petitti 2000)
            </h3>
            <p className="text-foreground leading-relaxed">
              Source: Overview of the Methods (Chapter 2) in Diana B. Petitti.{" "}
              <em>
                Meta-Analysis, Decision Analysis, and Cost-Effectiveness Analysis: Methods for
                Quantitative Synthesis in Medicine.
              </em>{" "}
              2nd ed. Monographs in Epidemiology and Biostatistics, v. 31. Oxford University
              Press, 2000.{" "}
              <a
                href="https://doi.org/10.1093/acprof:oso/9780195133646.001.0001"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                https://doi.org/10.1093/acprof:oso/9780195133646.001.0001
              </a>
              .
            </p>
            <p className="text-foreground leading-relaxed">
              For background, see: Tomás Aragón. &ldquo;Bayes&apos; Theorem and Decision Analysis
              for Mortals: Transforming Data into Information, Knowledge, and Wisdom - Part
              3.&rdquo; TEAM Public Health, January 15, 2016.{" "}
              <a
                href="https://teampublichealth.substack.com/p/bayes-theorem-and-decision-analysis"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                https://teampublichealth.substack.com/p/bayes-theorem-and-decision-analysis
              </a>
              .
            </p>
            <ul className="space-y-2 text-foreground">
              <li>
                DA using a decision tree (<code>rdecision</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Petitti2000/NB_R_rdecision_part1.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  R Jupyter Notebook (Part 1)
                </a>
              </li>
              <li>
                DA using a decision tree (<code>rdecision</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Petitti2000/NB_R_rdecision_part2.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  R Jupyter Notebook (Part 2)
                </a>
              </li>
              <li>
                DA using influence diagram (<code>DecisionProgramming.jl</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Petitti2000/NB_Julia_DecisionProgramming-jl.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Julia Jupyter Notebook
                </a>
              </li>
              <li>
                DA using agent-based modeling (<code>Agents.jl</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Petitti2000/NB_Julia_Agents-jl.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Julia Jupyter Notebook
                </a>
              </li>
            </ul>
          </CardContent>
        </Card>

        {/* Evans 1997 */}
        <Card className="bg-card border">
          <CardContent className="pt-6 pb-6 space-y-4">
            <h3 className="text-base font-semibold text-foreground">
              Elementary decision tree (Evans 1997)
            </h3>
            <p className="text-foreground leading-relaxed">
              We will replicate the decision analysis from this <code>rdecision</code> R package
              vignette:{" "}
              <a
                href="https://cran.r-project.org/web/packages/rdecision/vignettes/DT01-Sumatriptan.html"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                https://cran.r-project.org/web/packages/rdecision/vignettes/DT01-Sumatriptan.html
              </a>
              .
            </p>
            <p className="text-foreground leading-relaxed">
              Source: Evans, K. W., J. A. Boan, J. L. Evans, and A. Shuaib. &ldquo;Economic
              Evaluation of Oral Sumatriptan Compared with Oral Caffeine/Ergotamine for
              Migraine.&rdquo; <em>PharmacoEconomics</em> 12, no. 5 (1997): 565–77.{" "}
              <a
                href="https://doi.org/10.2165/00019053-199712050-00007"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                https://doi.org/10.2165/00019053-199712050-00007
              </a>
              .
            </p>
            <ul className="space-y-2 text-foreground">
              <li>
                DA using a decision tree (<code>rdecision</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Evans1997/NB_R_rdecision_Evans1997.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  R Jupyter Notebook
                </a>
              </li>
              <li>
                DA using influence diagram (<code>DecisionProgramming.jl</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Evans1997/NB_Julia_DecisionProgramming_Evans1997_V6.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Julia Jupyter Notebook
                </a>
              </li>
              <li>
                DA using influence diagram (<code>pyAgrum</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Evans1997/NB_Python_pyAgrum_Evans1997_V2.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Python Jupyter Notebook
                </a>
              </li>
              <li>
                DA using agent-based modeling (<code>Agents.jl</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Evans1997/NB_Julia_AgentsJL_Evans1997_V3_claude2.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Julia Jupyter Notebook
                </a>
              </li>
              <li>
                DA using agent-based modeling (<code>mesa</code>):{" "}
                <a
                  href="https://github.com/di4health/di4h/blob/main/nb/Evans1997/NB_Python_Mesa3_Evans1997_V1.ipynb"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-primary"
                >
                  Python Jupyter Notebook
                </a>
              </li>
            </ul>
          </CardContent>
        </Card>
      </section>

      <Separator />

      {/* ── NEAPOLITAN 2016 – PENDING ─────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">
          A Primer on Bayesian Decision Analysis (Neapolitan 2016) – PENDING
        </h2>
        <Card className="bg-card border">
          <CardContent className="pt-6 pb-6">
            <p className="text-foreground leading-relaxed">
              Source: Neapolitan, Richard, Xia Jiang, Daniela P. Ladner, and Bruce Kaplan.
              &ldquo;A Primer on Bayesian Decision Analysis With an Application to a Kidney
              Transplant Decision.&rdquo; <em>Transplantation</em> 100, no. 3 (2016): 489–96.{" "}
              <a
                href="https://doi.org/10.1097/TP.0000000000001145"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                https://doi.org/10.1097/TP.0000000000001145
              </a>
              .
            </p>
          </CardContent>
        </Card>
      </section>

      <Separator />

      {/* ── APPENDIX ──────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Appendix</h2>
        <Card className="bg-card border">
          <CardContent className="pt-6 pb-6 space-y-4">
            <h3 className="text-base font-semibold text-foreground">
              Open Source library of published health economic models
            </h3>
            <p className="text-foreground leading-relaxed">
              The library is a curated list of{" "}
              <a
                href="https://www.notion.so/Open-Source-Model-Library-2e828f8fdfc08017a9fbc021b4ef6ba1"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                open-source health economic models
              </a>{" "}
              identified through a systematic review conducted by Henderson et al. (2025).
              <sup>1</sup> The purpose of this resource is to make these models easily accessible
              for decision makers and modeling.
            </p>
            <p className="text-foreground leading-relaxed">
              To learn more watch this{" "}
              <a
                href="https://www.youtube.com/watch?v=_cGkw7ab7IA"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-primary"
              >
                YouTube video
              </a>{" "}
              by Mirko von Hein.
            </p>
          </CardContent>
        </Card>
      </section>

      <Separator />

      {/* ── FOOTNOTES ─────────────────────────────────────────────────────── */}
      <footer className="space-y-1 pb-8">
        <p className="text-xs text-muted-foreground">
          1. Henderson, Raymond H., Chris Sampson, Xavier G. L. V. Pouwels, et al.
          &ldquo;Mapping the Landscape of Open Source Health Economic Models: A Systematic
          Database Review and Analysis: An ISPOR Special Interest Group Report.&rdquo;{" "}
          <em>
            Value in Health: The Journal of the International Society for Pharmacoeconomics and
            Outcomes Research
          </em>{" "}
          28, no. 6 (2025): 813–20.{" "}
          <a
            href="https://doi.org/10.1016/j.jval.2025.01.019"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-primary"
          >
            https://doi.org/10.1016/j.jval.2025.01.019
          </a>
          .
        </p>
      </footer>

    </main>
  );
}
