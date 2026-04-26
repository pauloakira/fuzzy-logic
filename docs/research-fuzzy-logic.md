Below is a **detailed markdown-style theory note** on fuzzy logic, combining your PCS5708 slides with external references.

# Fuzzy Logic Theory

## 1. Motivation

Classical logic works with binary truth values:

- `0` = false
- `1` = true

This is useful for precise statements such as:

> “3 is a prime number.”

But many real-world concepts are vague:

> “The room is hot.”
> “The person is tall.”
> “The train is close.”
> “The speed is high.”

These statements are not always fully true or fully false. A temperature of 30°C may be “hot” to some degree, while 40°C may be “very hot.” Fuzzy logic was developed to model this kind of approximate reasoning. The Stanford Encyclopedia of Philosophy describes fuzzy logic as a family of many-valued logics where truth values represent **degrees of truth**, often in the interval `[0,1]`. ([Stanford Encyclopedia of Philosophy][1])

Your PCS5708 material defines fuzzy logic, or _lógica nebulosa_, as an AI tool that allows the manipulation of imprecise data labeled with linguistic meanings and associated with membership functions.

---

## 2. Crisp Sets vs. Fuzzy Sets

### 2.1 Crisp Sets

In classical set theory, membership is binary.

For a set `A` and an element `x`:

```text
x ∈ A  → true
x ∉ A  → false
```

Example:

```text
A = set of people taller than 1.80 m
```

A person who is 1.81 m belongs to the set.
A person who is 1.79 m does not belong to the set.

This creates a hard boundary.

### 2.2 Fuzzy Sets

A fuzzy set allows partial membership.

Instead of saying only:

```text
belongs / does not belong
```

we say:

```text
belongs with degree μ(x)
```

where:

```text
μ(x) ∈ [0,1]
```

A fuzzy set assigns a membership degree, typically a real number between 0 and 1, to each element of a universe. ([Stanford Encyclopedia of Philosophy][1])

Example:

```text
Set: Tall people
Person A: 1.50 m → μ(tall) = 0
Person B: 1.70 m → μ(tall) = 0.5
Person C: 1.85 m → μ(tall) = 1
```

This is exactly the kind of example shown in your slides: sets such as “tall people,” “thin people,” and “adolescents” do not always have sharp boundaries.

---

## 3. Membership Functions

A **membership function** maps each numerical value to a degree of membership.

Formally:

```text
μA : X → [0,1]
```

where:

- `X` is the universe of discourse,
- `A` is the fuzzy set,
- `μA(x)` is the degree to which `x` belongs to `A`.

Your slides show this structure visually: a fuzzy set has a **support**, a **core/body**, and **boundaries**.

### 3.1 Support

The **support** of a fuzzy set is the region where membership is greater than zero.

```text
support(A) = {x ∈ X | μA(x) > 0}
```

### 3.2 Core

The **core** is the region where membership is equal to one.

```text
core(A) = {x ∈ X | μA(x) = 1}
```

### 3.3 Boundary

The **boundary** is the region where membership is between zero and one.

```text
boundary(A) = {x ∈ X | 0 < μA(x) < 1}
```

This boundary region is where fuzzy logic is most useful, because it represents gradual transition rather than a sudden cutoff.

---

## 4. Common Membership Function Shapes

Fuzzy systems often use simple geometric functions because they are easy to interpret and compute.

### 4.1 Triangular Membership Function

A triangular function is defined by three points:

```text
(a, b, c)
```

where:

- `a` = left point where membership begins,
- `b` = peak where membership is 1,
- `c` = right point where membership returns to 0.

Example:

```text
Temperature is warm:
a = 20°C
b = 25°C
c = 30°C
```

So:

```text
20°C → not warm
25°C → fully warm
30°C → not warm
```

Values between these points have partial membership.

### 4.2 Trapezoidal Membership Function

A trapezoidal function has four points:

```text
(a, b, c, d)
```

It rises from 0 to 1, stays at 1 for a range, and then falls back to 0.

This is useful for concepts that have a plateau, such as:

```text
“comfortable temperature”
```

Maybe temperatures from 22°C to 26°C are all fully comfortable.

### 4.3 Gaussian Membership Function

A Gaussian function is smooth and bell-shaped.

It is useful when transitions should be gradual and differentiable, especially in adaptive or learning-based systems.

---

## 5. Linguistic Variables

A **linguistic variable** is a variable whose values are words instead of just numbers.

Example:

```text
Variable: Temperature
Linguistic values: Cold, Mild, Hot
```

Another example:

```text
Variable: Speed
Linguistic values: Low, Medium, High
```

Your PCS5708 slides emphasize this concept using labels such as:

```text
Grande
Quente
Lento
Pouco
```

These correspond to human-style concepts such as “large,” “hot,” “slow,” and “little.”

The point is that fuzzy logic lets us build systems using rules that look like human reasoning:

```text
IF temperature is high THEN fan speed is fast.
```

---

## 6. Fuzzy Propositions

In classical logic, a proposition is either true or false.

Example:

```text
João is short.
```

In fuzzy logic, a proposition has a degree of truth.

Example:

```text
João is short with degree 0.7.
```

Your slides explain that in fuzzy logic, a characteristic is always accompanied by a membership function or membership degree.

So fuzzy propositions are not simply:

```text
true / false
```

They are:

```text
true to some degree
```

---

## 7. Fuzzification

**Fuzzification** is the process of converting crisp numerical inputs into fuzzy values.

Example:

```text
Input: temperature = 28°C
```

After fuzzification:

```text
cold = 0.0
warm = 0.4
hot = 0.7
```

The same input can belong to multiple fuzzy sets at the same time.

Your slides give the example:

```text
“Fulano weighs 70 kg”
```

becoming:

```text
“Fulano is thin with membership degree 0.5”
```

This is a direct example of fuzzification.

---

## 8. Fuzzy Logical Operators

Fuzzy logic extends classical logical operators such as:

```text
AND
OR
NOT
IF ... THEN
```

The standard fuzzy interpretations often use:

```text
AND → minimum
OR  → maximum
NOT → complement
```

The Stanford Encyclopedia notes that a natural fuzzy interpretation is:

```text
x AND y = min(x, y)
x OR y  = max(x, y)
NOT x   = 1 - x
```

([Stanford Encyclopedia of Philosophy][1])

### 8.1 AND Operator

If:

```text
μA(x) = 0.7
μB(x) = 0.4
```

then:

```text
μA AND B(x) = min(0.7, 0.4) = 0.4
```

Meaning: the combined truth of both conditions is limited by the weaker one.

### 8.2 OR Operator

If:

```text
μA(x) = 0.7
μB(x) = 0.4
```

then:

```text
μA OR B(x) = max(0.7, 0.4) = 0.7
```

Meaning: the combined truth of either condition is the stronger one.

### 8.3 NOT Operator

If:

```text
μA(x) = 0.7
```

then:

```text
μNOT A(x) = 1 - 0.7 = 0.3
```

Your slides also present these operators as connections between fuzzy propositions: `A AND B`, `A OR B`, `NOT A`, and `IF A THEN B`.

---

## 9. Fuzzy Rules

Fuzzy systems usually work through rules of the form:

```text
IF antecedent THEN consequent
```

Example:

```text
IF temperature is high THEN fan speed is fast.
```

With multiple inputs:

```text
IF temperature is high AND humidity is high
THEN fan speed is very fast.
```

In fuzzy logic:

- the antecedent does not need to be fully true;
- the rule can fire partially;
- the consequent is activated according to the rule strength.

ScienceDirect describes fuzzy inference as mapping inputs to outputs using membership functions, fuzzy operators, and IF–THEN rules. ([ScienceDirect][2])

---

## 10. Rule Strength

The **rule strength** tells us how strongly a rule applies.

Example:

```text
Rule:
IF temperature is high AND humidity is high
THEN fan speed is fast
```

Suppose:

```text
temperature is high = 0.8
humidity is high = 0.6
```

Using fuzzy AND as minimum:

```text
rule strength = min(0.8, 0.6) = 0.6
```

So the rule fires with strength `0.6`.

This means the output fuzzy set “fast fan speed” will be activated at degree `0.6`.

---

## 11. Fuzzy Inference

**Fuzzy inference** is the process of applying fuzzy rules to fuzzy inputs to generate fuzzy outputs.

A typical fuzzy inference system contains:

```text
crisp inputs
→ fuzzification
→ rule evaluation
→ implication
→ aggregation
→ defuzzification
→ crisp output
```

ScienceDirect summarizes fuzzy inference as involving five main parts: fuzzification, application of fuzzy operators, implication, aggregation, and defuzzification. ([ScienceDirect][2])

Your slides show a similar fuzzy inference system architecture:

```text
input variables
→ fuzzification
→ fuzzy logic controller
→ defuzzification
→ output variables
```

---

## 12. Implication

After the antecedent of a rule is evaluated, the rule strength is applied to the consequent.

Example:

```text
IF service is good THEN tip is high
```

Suppose:

```text
service is good = 0.6
```

Then the consequent:

```text
tip is high
```

is activated with degree `0.6`.

In Mamdani-style systems, this often means clipping or scaling the output membership function.

Your slides show this idea through fuzzy implication and generalized modus ponens: if `A` is true to a certain degree and `A → B`, then `B` is inferred to a corresponding degree.

---

## 13. Aggregation

A fuzzy system usually has many rules.

Example:

```text
Rule 1:
IF service is poor THEN tip is low

Rule 2:
IF service is average THEN tip is medium

Rule 3:
IF service is excellent THEN tip is high
```

Each rule produces a fuzzy output. These outputs must be combined into one final fuzzy set.

This process is called **aggregation**.

Usually, fuzzy OR / maximum is used to combine the activated output sets.

---

## 14. Defuzzification

After inference and aggregation, the output is still fuzzy.

Example:

```text
tip is low with degree 0.2
tip is medium with degree 0.6
tip is high with degree 0.4
```

But a real system often needs a crisp numerical output:

```text
tip = 17%
```

**Defuzzification** converts the fuzzy output into a crisp value.

Your slides define defuzzification as the process that transforms a linguistic variable associated with a fuzzy set into a physical numerical quantity.

Common methods include:

```text
centroid / center of gravity
weighted average of maxima
first of maxima
```

These methods are also listed in your PCS5708 slides.

### 14.1 Centroid Method

The centroid method finds the center of mass of the aggregated fuzzy output.

Conceptually:

```text
crisp output = balance point of the fuzzy area
```

This is one of the most common methods because it considers the whole shape of the output fuzzy set.

---

## 15. Mamdani Fuzzy Inference

The **Mamdani** method is one of the most common fuzzy inference approaches.

It is especially intuitive because both inputs and outputs are represented using fuzzy sets.

A Mamdani rule looks like this:

```text
IF temperature is high AND humidity is high
THEN fan speed is fast
```

The output of each rule is a fuzzy set. The rule outputs are aggregated, and then defuzzification is used to produce a crisp output. MathWorks describes Mamdani systems as intuitive, well-suited to human input, and widely accepted. ([MathWorks][3])

Mamdani systems are useful when expert knowledge can be expressed in linguistic rules.

Example:

```text
IF distance is small AND speed is high
THEN brake is strong
```

This kind of rule is very natural for control systems.

---

## 16. Sugeno Fuzzy Inference

The **Sugeno**, or **Takagi–Sugeno–Kang**, method is another major fuzzy inference approach.

In a Sugeno system, the consequent is usually a constant or a mathematical function of the inputs.

Example with constant output:

```text
IF temperature is high THEN fan speed = 80
```

Example with linear output:

```text
IF temperature is high THEN fan speed = 2x + 5
```

MathWorks notes that Sugeno systems are computationally efficient and work well with optimization, adaptive techniques, PID control, and mathematical analysis. ([MathWorks][3])

A simplified Sugeno output can be computed as a weighted average:

```text
output = Σ(wi zi) / Σ(wi)
```

where:

- `wi` = firing strength of rule `i`,
- `zi` = output value of rule `i`.

Sugeno systems are often preferred when computational efficiency or smooth mathematical control is important.

---

## 17. Mamdani vs. Sugeno

| Feature            | Mamdani                          | Sugeno                                  |
| ------------------ | -------------------------------- | --------------------------------------- |
| Output type        | Fuzzy set                        | Constant or function                    |
| Interpretability   | Very high                        | Medium                                  |
| Human readability  | Excellent                        | Good                                    |
| Defuzzification    | Usually required                 | Often built into weighted average       |
| Computational cost | Higher                           | Lower                                   |
| Common use         | Expert systems, human-like rules | Control, optimization, adaptive systems |

Mamdani is usually easier to explain to humans. Sugeno is often easier to integrate with mathematical models or adaptive systems.

---

## 18. Fuzzy Control Systems

Fuzzy logic is widely used in control systems because many control decisions can be expressed linguistically.

Example:

```text
IF error is large AND error change is positive
THEN control action is strong negative
```

A fuzzy controller usually has:

```text
1. input variables
2. input membership functions
3. rule base
4. inference mechanism
5. output membership functions
6. defuzzification method
```

Your slides describe fuzzy control systems and later apply fuzzy logic to train-control-like situations using variables such as distance, velocity, braking, neutral action, and propulsion.

Example rule:

```text
IF distance is small AND velocity is high
THEN brake is maximum
```

This is a typical fuzzy-control idea: the system does not need an exact equation for every situation. It can use expert-like rules.

---

## 19. Example: Fuzzy Tip System

Suppose we want to determine a restaurant tip.

### Inputs

```text
service quality: poor, average, excellent
food quality: bad, good, delicious
```

### Output

```text
tip: low, medium, high
```

### Rules

```text
Rule 1:
IF service is poor OR food is bad
THEN tip is low

Rule 2:
IF service is average
THEN tip is medium

Rule 3:
IF service is excellent AND food is delicious
THEN tip is high
```

### Example Input

```text
service = 8/10
food = 7/10
```

After fuzzification:

```text
service is average = 0.3
service is excellent = 0.7

food is good = 0.5
food is delicious = 0.6
```

Rule 3 strength:

```text
min(0.7, 0.6) = 0.6
```

So:

```text
tip is high with degree 0.6
```

After all rules are evaluated and aggregated, defuzzification might produce:

```text
tip = 18%
```

---

## 20. Fuzzy Logic vs. Probability

Fuzzy logic and probability are often confused, but they model different things.

### Probability

Probability describes uncertainty about whether something is true.

Example:

```text
There is a 70% chance that it will rain tomorrow.
```

This means we are uncertain about the event.

### Fuzzy Logic

Fuzzy logic describes the degree to which a vague statement is true.

Example:

```text
Today is hot with degree 0.7.
```

This does not mean there is a 70% chance today is hot. It means today partially satisfies the concept “hot.”

So:

```text
Probability → uncertainty about occurrence
Fuzzy logic → vagueness of meaning
```

---

## 21. Advantages of Fuzzy Logic

Fuzzy logic is useful because it:

```text
handles vague concepts naturally
uses human-readable rules
does not always require precise mathematical models
works well in control systems
can combine expert knowledge with numerical inputs
is interpretable compared with many black-box AI models
```

This matches the conclusion in your slides: fuzzy logic formalizes approximate reasoning in a way that is close to human thinking.

---

## 22. Limitations of Fuzzy Logic

Fuzzy logic also has limitations:

```text
membership functions can be subjective
rule bases can become large
poorly designed rules can produce poor results
tuning may require expert knowledge
it may be less suitable for problems where precise probabilistic uncertainty is needed
```

In safety-critical systems, fuzzy logic may also face certification and regulatory challenges. Your PCS5708 slides mention that some European standards do not permit AI tools in critical control systems.

---

## 23. General Design Process

A typical fuzzy system can be designed as follows:

```text
1. Define the problem
2. Choose input and output variables
3. Define linguistic terms
4. Create membership functions
5. Build fuzzy IF–THEN rules
6. Select inference method
7. Select defuzzification method
8. Test and tune the system
9. Validate with real or simulated data
```

Your slides describe a similar design process: dimensioning the system in terms of input variables, output variables, control variables, expert knowledge, system observation, measurements, and monitoring.

---

## 24. Summary

Fuzzy logic is a mathematical framework for reasoning with vague, imprecise, or linguistic concepts.

The core ideas are:

```text
fuzzy set       → set with gradual membership
membership     → degree between 0 and 1
linguistic term → word like high, low, hot, cold
fuzzification  → crisp input to fuzzy values
rule base      → IF–THEN rules
inference      → applying rules to inputs
aggregation    → combining rule outputs
defuzzification → fuzzy output to crisp output
```

The essential flow is:

```text
crisp input
→ fuzzification
→ fuzzy inference
→ aggregation
→ defuzzification
→ crisp output
```

The main intuition is simple:

> Fuzzy logic lets machines reason with concepts that are not sharply defined, using rules that resemble human reasoning.

---

# Part II — Extended Topics

The sections above sketch the core of fuzzy logic. The material that follows extends that sketch with topics directly relevant to the implementation tracks in this repository:

- The **third major inference style** (Tsukamoto), which sits between Mamdani and Sugeno.
- The **algebraic generalization** of fuzzy AND/OR (t-norm and t-conorm families), which lets the same FIS run with different operator choices.
- **Foundational tools** — α-cuts, hedges, generalized modus ponens — that show up whenever you implement or debug a fuzzy system.
- Additional **membership function shapes** and **defuzzification formulas** in their explicit form.
- **Neuro-fuzzy systems** (ANFIS), which encode a fuzzy inference system as a differentiable computation graph and learn it from data.

---

## 25. Tsukamoto Fuzzy Inference

Beyond Mamdani (Section 15) and Sugeno (Section 16), the **Tsukamoto** method is a third inference style. It is less common but useful when each output fuzzy set has a **monotonic** membership function.

A Tsukamoto rule has the same look as a Mamdani rule:

```text
IF service is excellent THEN tip is high
```

The constraint is that the consequent fuzzy set "tip is high" must have a *monotonic* MF — for example, a sigmoid that rises from 0 to 1.

### 25.1 Inference Mechanism

The key idea: because the consequent MF is monotonic, the firing strength of a rule directly maps to a single crisp output. If rule `i` fires with strength `wi` and the consequent MF is `μi`, the rule produces:

```text
zi = μi^{-1}(wi)
```

The system output is then a weighted average:

```text
output = Σ(wi · zi) / Σ(wi)
```

This sidesteps both Mamdani's aggregation+defuzzification and Sugeno's explicit functional consequent.

### 25.2 Comparison

| Aspect             | Mamdani              | Sugeno                  | Tsukamoto                  |
| ------------------ | -------------------- | ----------------------- | -------------------------- |
| Consequent         | Fuzzy set            | Constant or function    | Monotonic fuzzy set        |
| Output computation | Aggregate + defuzz   | Weighted average        | Weighted average via μ⁻¹   |
| Interpretability   | High                 | Medium                  | Medium                     |
| Computational cost | High                 | Low                     | Low                        |
| Restriction        | None                 | Crisp consequent form   | Monotonic consequent MF    |

**When to use**: when inputs are linguistic but the monotone-consequent constraint is acceptable, and a balance between Mamdani's interpretability and Sugeno's efficiency is desired.

**Limitation**: monotonic MFs are restrictive. If the natural output concept is non-monotonic (e.g., "comfortable temperature" peaks in the middle), Tsukamoto cannot represent it directly.

---

## 26. Properties of Fuzzy Sets and α-Cuts

Beyond the **support**, **core**, and **boundary** introduced in Section 3, several additional properties are useful in design and analysis.

### 26.1 Height

The **height** of a fuzzy set `A` is the supremum of its membership function:

```text
height(A) = sup { μA(x) | x ∈ X }
```

### 26.2 Normality

A fuzzy set is **normal** if its height is 1 — at least one element has full membership:

```text
A is normal ⇔ ∃ x ∈ X such that μA(x) = 1
```

Non-normal sets can be normalized by dividing by the height.

### 26.3 Convexity

A fuzzy set on the real line is **convex** if its membership function is unimodal:

```text
A convex ⇔ for all x1 < x2 < x3, μA(x2) ≥ min(μA(x1), μA(x3))
```

Triangular, trapezoidal, Gaussian, and bell-shaped MFs are convex; bimodal MFs are not.

### 26.4 Cardinality

The **scalar cardinality** of a fuzzy set is the sum (or integral) of memberships:

```text
|A| = Σ_x μA(x)        (discrete universe)
|A| = ∫ μA(x) dx       (continuous universe)
```

### 26.5 α-Cuts

An **α-cut** of `A` at level `α ∈ [0, 1]` is the crisp set of elements with membership at least `α`:

```text
A_α = { x ∈ X | μA(x) ≥ α }
```

The **strict α-cut** uses strict inequality:

```text
A_α^+ = { x ∈ X | μA(x) > α }
```

α-cuts are the bridge between fuzzy and crisp operations: many fuzzy algorithms can be expressed as families of crisp operations, one per α level, then combined.

**Properties**:

- `A_0` is the universe (or its closure).
- `A_1` is the core of `A`.
- α-cuts are nested: if `α1 ≤ α2` then `A_{α1} ⊇ A_{α2}`.

**Practical use**: discretization grids in Mamdani aggregation can be replaced by a finite ladder of α-cuts, often more numerically stable than fixed grids.

---

## 27. t-norm and t-conorm Families

Section 8 introduced AND/OR/NOT using `min`, `max`, and `1 - x`. These are one specific choice — they belong to broader algebraic families. Real fuzzy systems often need to swap the family without rewriting their inference logic.

### 27.1 t-norm Axioms

A function `T : [0,1] × [0,1] → [0,1]` is a **t-norm** if it satisfies:

- **Commutativity**: `T(a, b) = T(b, a)`
- **Associativity**: `T(T(a, b), c) = T(a, T(b, c))`
- **Monotonicity**: if `a ≤ a'` then `T(a, b) ≤ T(a', b)`
- **Boundary**: `T(a, 1) = a`

t-norms generalize fuzzy AND.

### 27.2 t-conorm Axioms

A **t-conorm** (or s-norm) `S` satisfies the same first three axioms with the boundary condition `S(a, 0) = a`. t-conorms generalize fuzzy OR.

### 27.3 Common Families

| Family                  | t-norm `T(a, b)`             | t-conorm `S(a, b)`               |
| ----------------------- | ----------------------------- | --------------------------------- |
| Min/max (Zadeh, Gödel)  | `min(a, b)`                   | `max(a, b)`                       |
| Product (probabilistic) | `a · b`                       | `a + b - a·b`                     |
| Łukasiewicz             | `max(a + b - 1, 0)`           | `min(a + b, 1)`                   |
| Drastic                 | `a if b=1, b if a=1, else 0`  | `a if b=0, b if a=0, else 1`      |
| Hamacher (γ ≥ 0)        | `a·b / (γ + (1-γ)(a+b - a·b))` | (De Morgan dual)                |
| Yager (p > 0)           | `1 - min(1, ((1-a)^p + (1-b)^p)^{1/p})` | `min(1, (a^p + b^p)^{1/p})` |

### 27.4 De Morgan Duality

For any t-norm `T` and complement `c(x) = 1 - x`, the **De Morgan dual** t-conorm is:

```text
S(a, b) = 1 - T(1 - a, 1 - b)
```

`min/max` and `1 - x` form a De Morgan triple, as do `product` and `probabilistic-sum`.

### 27.5 Choice of Family

- **Min/max** — classical, idempotent, easy to interpret, but not differentiable at the kink.
- **Product** — smooth and differentiable; multiplicative structure is natural for probabilistic interpretations and for gradient-based learning. ANFIS typically uses product for rule firing.
- **Łukasiewicz** — bounded; captures hard saturation. Useful when crossing thresholds matters.
- **Yager / Hamacher** — parametric families that interpolate between extremes; useful for tuning.

**Practical default**: `min/max` for human-readable Mamdani; `product` for ANFIS and any neuro-fuzzy system where gradients flow through the operator.

---

## 28. Linguistic Hedges

A **hedge** is a modifier applied to a linguistic term to produce a new fuzzy set, encoding adverbs like *very*, *somewhat*, *more or less*.

A common formulation defines each hedge as a transformation of the membership function:

```text
very A         → μA(x)^2
somewhat A     → μA(x)^{1/2}
extremely A    → μA(x)^3
more or less A → μA(x)^{1/2}
not A          → 1 - μA(x)
```

Example: if `μ_tall(1.85) = 0.7`, then:

```text
μ_{very tall}(1.85)     = 0.7^2     = 0.49
μ_{somewhat tall}(1.85) = 0.7^{1/2} ≈ 0.84
```

Hedges let a small base vocabulary cover a much richer set of linguistic terms without authoring new MFs by hand. They compose: `very somewhat tall` is well-defined, even if the linguistic interpretation needs care.

---

## 29. Generalized Modus Ponens

In classical logic, **modus ponens** is:

```text
A → B
A
∴ B
```

The **generalized modus ponens** (GMP) is its fuzzy extension. Given:

```text
Rule:   IF X is A THEN Y is B
Fact:   X is A'
```

where `A'` is *similar to but not identical to* `A`, GMP infers:

```text
Y is B'
```

where `B'` depends on a fuzzy implication operator and a composition rule. The standard formulation uses **max-min composition**:

```text
μ_{B'}(y) = sup_x  min( μ_{A'}(x),  μ_{A → B}(x, y) )
```

Different choices of fuzzy implication operator yield different inference behaviors:

| Implication      | `μ_{A → B}(x, y)`                      | Notes                              |
| ---------------- | --------------------------------------- | ---------------------------------- |
| Mamdani          | `min(μA(x), μB(y))`                     | Used in Mamdani FIS                |
| Łukasiewicz      | `min(1, 1 - μA(x) + μB(y))`             | Bounded, residuated                |
| Gödel            | `1 if μA(x) ≤ μB(y), else μB(y)`        | Discontinuous                      |
| Goguen (product) | `1 if μA(x) ≤ μB(y), else μB(y)/μA(x)`  | Smooth, used in some Sugeno models |

Mamdani-style FIS implements the first row at scale; classical fuzzy inference theory often uses the others. The choice affects how a partially-matched antecedent propagates uncertainty into the consequent.

---

## 30. Additional Membership Function Shapes

Section 4 covered triangular, trapezoidal, and Gaussian MFs. Other commonly used shapes:

### 30.1 Generalized Bell

```text
μ(x; a, b, c) = 1 / ( 1 + |(x - c) / a|^{2b} )
```

Smooth, symmetric, and parametric (`a` controls width, `b` controls slope sharpness, `c` is the center). Used heavily in ANFIS for its smooth gradients.

### 30.2 Sigmoid

```text
μ(x; a, c) = 1 / ( 1 + exp(-a (x - c)) )
```

Monotonic — useful for Tsukamoto consequents and for "open-ended" linguistic terms like *high* or *large* that saturate above some threshold.

### 30.3 Singleton

A degenerate fuzzy set with membership 1 at a single point and 0 elsewhere:

```text
μ(x; c) = 1 if x = c, else 0
```

Used in zero-order Sugeno consequents.

### 30.4 Choice for Learning Systems

For ANFIS and other gradient-trained neuro-fuzzy models, prefer **Gaussian** or **bell** shapes — both are smooth and have well-conditioned gradients. Triangular and trapezoidal MFs have non-differentiable kinks that complicate gradient-based optimization (subgradients work but are noisier).

---

## 31. Defuzzification Methods (Formal)

Section 14 introduced defuzzification conceptually. For an aggregated output fuzzy set with membership `μ(y)` over a universe `Y`, the standard methods have explicit formulas.

### 31.1 Centroid (Center of Gravity)

```text
y* = ∫ y · μ(y) dy / ∫ μ(y) dy
```

Smooth; considers the entire distribution. Standard default.

### 31.2 Bisector

The value `y*` such that the area under `μ` is split into equal halves:

```text
∫_{y_min}^{y*} μ(y) dy = ∫_{y*}^{y_max} μ(y) dy
```

Robust to outliers in the tails of `μ`.

### 31.3 Mean of Maximum (MoM)

```text
y* = mean { y ∈ Y | μ(y) = max_y μ(y) }
```

### 31.4 Smallest of Maximum (SoM) and Largest of Maximum (LoM)

```text
y*_SoM = min { y ∈ Y | μ(y) = max_y μ(y) }
y*_LoM = max { y ∈ Y | μ(y) = max_y μ(y) }
```

Useful when the application has a directional bias — e.g., a conservative controller picks SoM, an aggressive one picks LoM.

### 31.5 Numerical Notes

- Centroid and bisector require a **discretization grid** over `Y`. Coarse grids give visibly different answers; treat the grid as a first-class config argument, never hardcoded.
- On a degenerate aggregated output (`μ ≡ 0`), centroid is undefined. Convention used in this repo: return the universe midpoint and emit a warning.
- For triangular and trapezoidal aggregated shapes, closed-form centroid expressions exist and avoid grid discretization entirely.

---

## 32. Neuro-fuzzy Systems and ANFIS

A natural question: can a fuzzy system be **learned from data** rather than authored from expert knowledge? Neuro-fuzzy systems answer yes, by encoding a fuzzy inference system as a differentiable computation graph and training its parameters with gradient descent.

### 32.1 ANFIS Architecture

**ANFIS** (Adaptive Neuro-Fuzzy Inference System, Jang 1993) encodes a first-order **Sugeno** FIS as a 5-layer feed-forward network:

```text
Layer 1  Fuzzification     input x_i passes through learnable MFs (Gaussian or bell)
Layer 2  Rule firing       t-norm (typically product) of antecedent memberships → w_i
Layer 3  Normalization     w̄_i = w_i / Σ_j w_j
Layer 4  Consequent        f_i = p_i · x + q_i  (linear in inputs)
Layer 5  Output            y = Σ_i  w̄_i · f_i
```

All operations are differentiable. The MF parameters (Layer 1) and consequent parameters (Layer 4) are learned. Layers 2, 3, 5 have no learnable parameters.

### 32.2 Hybrid vs. End-to-End Training

The original ANFIS uses a **hybrid** scheme:

- **Forward pass**: with current MF parameters fixed, the consequent parameters are solved by **least squares** (the output is linear in them).
- **Backward pass**: with consequents fixed, the MF parameters are updated by gradient descent.

Modern PyTorch implementations often use **end-to-end SGD** for simplicity, accepting some loss of convergence speed in exchange for flexibility (custom losses, regularization, deep stacking, batch training).

### 32.3 Numerical Pitfalls

- **Positive parameters** (Gaussian widths, bell `a`): parameterize via `softplus(raw) + ε`. Never `abs()` or `clamp(min=0)` — both break gradients near zero.
- **Normalization**: Layer 3's division should use `softmax` or a `logsumexp`-stabilized form. Raw `exp / sum(exp)` underflows when firing strengths are tiny.
- **Half-precision** (fp16/bf16): avoid in the firing-strength normalization layer; MFs are tail-sensitive and the normalization can amplify rounding noise.

### 32.4 Trade-offs vs. Classical FIS

| Aspect           | Classical FIS              | ANFIS                                 |
| ---------------- | -------------------------- | ------------------------------------- |
| Knowledge source | Expert                     | Data                                  |
| MFs              | Hand-designed              | Learned                               |
| Rules            | Hand-written               | Implicit in network structure         |
| Interpretability | High                       | Medium (rules visible, params opaque) |
| Data requirement | None                       | Substantial                           |
| Generalization   | Bounded by expert quality  | Bounded by data quality               |

ANFIS sits between a black-box neural network (no interpretability, all data-driven) and a hand-authored FIS (full interpretability, no data). The fuzzy structure provides a useful inductive bias for low-data regimes.

### 32.5 Beyond ANFIS

Other neuro-fuzzy variants worth knowing:

- **CANFIS** — extends ANFIS to multiple correlated outputs.
- **TSK fuzzy networks** — generalize ANFIS to broader Takagi–Sugeno–Kang structures.
- **Type-2 ANFIS** — uses interval type-2 MFs to model uncertainty in the MFs themselves.
- **Deep neuro-fuzzy** — stacks multiple fuzzy layers, sometimes with attention or convolutional structure.

---

## 33. Brief Notes on Adjacent Areas

### 33.1 Type-2 Fuzzy Sets

In a **type-2 fuzzy set**, the membership value at each point is itself a fuzzy set (or, in *interval type-2*, an interval). This models uncertainty in the membership function — useful when expert MFs disagree, or when noisy data makes the boundary location uncertain. Type-2 systems are computationally heavier and require a *type-reduction* step before defuzzification.

### 33.2 Fuzzy Clustering

**Fuzzy c-means (FCM)** generalizes k-means: each data point belongs to every cluster with a degree of membership rather than a hard assignment. The objective is:

```text
J = Σ_i Σ_j  μ_{ij}^m · ||x_i - c_j||^2
```

with `m > 1` controlling fuzziness. FCM is widely used to *initialize* fuzzy systems by deriving rule antecedents from cluster centroids.

### 33.3 Fuzzy Logic vs. Probability — Revisited

Section 20 distinguished the two by interpretation. A finer point: their *operations* can numerically coincide. Fuzzy AND under the product t-norm gives `a · b`, which equals probabilistic AND under independence. But the *meaning* differs — one is a graded membership, the other a frequency or belief about a binary event. Choosing the same numerical operator does not collapse the conceptual distinction; the consumer of the value still has to know which interpretation applies.

---

## 34. Notation and Conventions

Throughout this document:

- `μA(x)` is the membership function of fuzzy set `A` evaluated at `x`.
- `X` is the universe of discourse (domain of inputs); `Y` is the output universe.
- `T` denotes a t-norm; `S` a t-conorm; `c` a complement.
- `A_α` denotes the α-cut of `A` (Section 26.5), not matrix indexing.
- "The slides" refers to the user's PCS5708 lecture material.

---

[1]: https://plato.stanford.edu/entries/logic-fuzzy/ "
Fuzzy Logic (Stanford Encyclopedia of Philosophy)
"
[2]: https://www.sciencedirect.com/topics/engineering/fuzzy-inference "Fuzzy Inference - an overview | ScienceDirect Topics"
[3]: https://www.mathworks.com/help/fuzzy/types-of-fuzzy-inference-systems.html "Mamdani and Sugeno Fuzzy Inference Systems - MATLAB & Simulink
"
