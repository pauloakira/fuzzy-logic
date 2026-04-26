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

[1]: https://plato.stanford.edu/entries/logic-fuzzy/ "
Fuzzy Logic (Stanford Encyclopedia of Philosophy)
"
[2]: https://www.sciencedirect.com/topics/engineering/fuzzy-inference "Fuzzy Inference - an overview | ScienceDirect Topics"
[3]: https://www.mathworks.com/help/fuzzy/types-of-fuzzy-inference-systems.html "Mamdani and Sugeno Fuzzy Inference Systems - MATLAB & Simulink
"
