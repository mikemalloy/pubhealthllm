export default function ResourcesPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-12 text-sm leading-relaxed">
      <h1 className="text-2xl font-semibold text-foreground">Resources</h1>

      {/* ── Software packages ── */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Software packages</h2>
        <p className="text-muted-foreground">
          The following open source software packages are used for decision modeling and leverage
          different approaches: decision trees, Bayesian networks (e.g., influence diagrams),
          mixed-integer linear programming (MILP) (i.e., optimization), and agent-based modeling.
        </p>
        <ol className="list-decimal list-inside space-y-1 text-foreground">
          <li>
            R:{" "}
            <a
              href="https://cran.r-project.org/web/packages/rdecision/index.html"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
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
              className="underline text-primary hover:opacity-80"
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
              className="underline text-primary hover:opacity-80"
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
              className="underline text-primary hover:opacity-80"
            >
              Agents.jl
            </a>
            : for agent-based modeling
          </li>
        </ol>
      </section>

      {/* ── Primer series ── */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">
          Primer on Medical Decision Analysis (5-part series)
        </h2>
        <ol className="list-decimal list-inside space-y-3 text-foreground">
          <li>
            Detsky, A. S., G. Naglie, M. D. Krahn, D. Naimark, and D. A. Redelmeier. &ldquo;Primer
            on Medical Decision Analysis: Part 1–Getting Started.&rdquo;{" "}
            <em>Medical Decision Making</em> 17, no. 2 (1997): 123–25.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9701700201"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9701700201
            </a>
            .
          </li>
          <li>
            Detsky, A. S., G. Naglie, M. D. Krahn, D. A. Redelmeier, and D. Naimark. &ldquo;Primer
            on Medical Decision Analysis: Part 2–Building a Tree.&rdquo;{" "}
            <em>Medical Decision Making</em> 17, no. 2 (1997): 126–35.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9701700202"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9701700202
            </a>
            .
          </li>
          <li>
            Naglie, G., M. D. Krahn, D. Naimark, D. A. Redelmeier, and A. S. Detsky. &ldquo;Primer
            on Medical Decision Analysis: Part 3–Estimating Probabilities and Utilities.&rdquo;{" "}
            <em>Medical Decision Making</em> 17, no. 2 (1997): 136–41.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9701700203"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9701700203
            </a>
            .
          </li>
          <li>
            Krahn, M. D., G. Naglie, D. Naimark, D. A. Redelmeier, and A. S. Detsky. &ldquo;Primer
            on Medical Decision Analysis: Part 4–Analyzing the Model and Interpreting the
            Results.&rdquo; <em>Medical Decision Making</em> 17, no. 2 (1997): 142–51.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9701700204"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9701700204
            </a>
            .
          </li>
          <li>
            Naimark, D., M. D. Krahn, G. Naglie, D. A. Redelmeier, and A. S. Detsky. &ldquo;Primer
            on Medical Decision Analysis: Part 5–Working with Markov Processes.&rdquo;{" "}
            <em>Medical Decision Making</em> 17, no. 2 (1997): 152–59.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9701700205"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9701700205
            </a>
            .
          </li>
        </ol>
      </section>

      {/* ── Individual articles ── */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Individual articles</h2>
        <ol className="list-decimal list-inside space-y-3 text-foreground">
          <li>
            Owens, D. K., R. D. Shachter, and R. F. Nease. &ldquo;Representation and Analysis of
            Medical Decision Problems with Influence Diagrams.&rdquo;{" "}
            <em>Medical Decision Making</em> 17, no. 3 (1997): 241–62.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9701700301"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9701700301
            </a>
            .
          </li>
          <li>
            Nease, R. F., and D. K. Owens. &ldquo;Use of Influence Diagrams to Structure Medical
            Decisions.&rdquo; <em>Medical Decision Making</em> 17, no. 3 (1997): 263–75.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9701700302"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9701700302
            </a>
            .
          </li>
          <li>
            Sonnenberg, F. A., and J. R. Beck. &ldquo;Markov Models in Medical Decision Making: A
            Practical Guide.&rdquo; <em>Medical Decision Making</em> 13, no. 4 (1993): 322–38.{" "}
            <a
              href="https://doi.org/10.1177/0272989X9301300409"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X9301300409
            </a>
            .
          </li>
          <li>
            Alarid-Escudero, Fernando, Eline Krijkamp, Eva A. Enns, et al. &ldquo;A Tutorial on
            Time-Dependent Cohort State-Transition Models in R Using a Cost-Effectiveness Analysis
            Example.&rdquo; <em>Medical Decision Making</em> 43, no. 1 (2023): 21–41.{" "}
            <a
              href="https://doi.org/10.1177/0272989X221121747"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X221121747
            </a>
            .
          </li>
          <li>
            Alarid-Escudero, Fernando, Eline Krijkamp, Eva A. Enns, et al. &ldquo;An Introductory
            Tutorial on Cohort State-Transition Models in R Using a Cost-Effectiveness Analysis
            Example.&rdquo; <em>Medical Decision Making</em> 43, no. 1 (2023): 3–20.{" "}
            <a
              href="https://doi.org/10.1177/0272989X221103163"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X221103163
            </a>
            .
          </li>
          <li>
            Jalal, Hawre, Petros Pechlivanoglou, Eline Krijkamp, Fernando Alarid-Escudero, Eva
            Enns, and M. G. Myriam Hunink. &ldquo;An Overview of R in Health Decision Sciences.&rdquo;{" "}
            <em>Medical Decision Making</em> 37, no. 7 (2017): 735–46.{" "}
            <a
              href="https://doi.org/10.1177/0272989X16686559"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X16686559
            </a>
            .
          </li>
          <li>
            Williams, Claire, James D. Lewsey, Andrew H. Briggs, and Daniel F. Mackay.
            &ldquo;Cost-Effectiveness Analysis in R Using a Multi-State Modeling Survival Analysis
            Framework: A Tutorial.&rdquo; <em>Medical Decision Making</em> 37, no. 4 (2017):
            340–52.{" "}
            <a
              href="https://doi.org/10.1177/0272989X16651869"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1177/0272989X16651869
            </a>
            .
          </li>
        </ol>
      </section>

      {/* ── Recommended books ── */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Recommended books</h2>
        <ol className="list-decimal list-inside space-y-3 text-foreground">
          <li>
            Duke, Annie. <em>How to Decide: Simple Tools for Making Better Choices.</em> Penguin
            Publishing Group, 2020.{" "}
            <a
              href="https://www.annieduke.com/books/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://www.annieduke.com/books/
            </a>
            .
          </li>
          <li>
            Sox, Harold C., Michael C. Higgins, Douglas K. Owens, and Gillian Sanders Schmidler.{" "}
            <em>Medical Decision Making.</em> Third edition. John Wiley &amp; Sons, Inc, 2024.{" "}
            <a
              href="https://doi.org/10.1002/9781119627876"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1002/9781119627876
            </a>
            .
          </li>
          <li>
            Hunink, M. G. Myriam. <em>Decision Making in Health and Medicine.</em> 2nd ed. With
            Milton C. Weinstein, Eve Wittenberg, Michael F. Drummond, Joseph S. Pliskin, John B.
            Wong, and Paul Glasziou. Cambridge University Press, 2014.{" "}
            <a
              href="https://doi.org/10.1017/CBO9781139506779"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1017/CBO9781139506779
            </a>
            .
          </li>
          <li>
            Parnell, Gregory S, Terry A. Bresnick, Eric Specking, Steven N. Tani, and Eric R.
            Johnson. <em>Handbook of Decision Analysis.</em> 2nd ed. Wiley, 2025.
          </li>
          <li>
            Arroyo, Paz, Annett Schöttle, and Randi Christensen.{" "}
            <em>Building Decisions: How Choosing by Advantages Drives Project Success.</em>{" "}
            Routledge, 2025.{" "}
            <a
              href="https://doi.org/10.1201/9781003518310"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://doi.org/10.1201/9781003518310
            </a>
            .
          </li>
          <li>
            Gray, Alastair, and Andrew Briggs, editors.{" "}
            <em>Handbooks in Health Economic Evaluation.</em> Oxford University Press.{" "}
            <a
              href="https://www.herc.ox.ac.uk/downloads/handbooks-in-health-economic-evaluation"
              target="_blank"
              rel="noopener noreferrer"
              className="underline text-primary hover:opacity-80"
            >
              https://www.herc.ox.ac.uk/downloads/handbooks-in-health-economic-evaluation
            </a>
            .
          </li>
        </ol>
      </section>
    </div>
  );
}
