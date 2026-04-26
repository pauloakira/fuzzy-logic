# Relatório — Controle ativo de vibrações em estrutura SDOF com lógica fuzzy

**PCS5708 — Exercício 2 — abordagem Mamdani**

> Conforme o enunciado, este relatório apresenta as quatro telas exigidas:
>
> 1. **Tela 1 — Variáveis de entrada** (§3)
> 2. **Tela 2 — Variável de saída** (§4)
> 3. **Tela 3 — Base de regras** (§5)
> 4. **Tela 4 — Exemplo de aplicação do sistema de controle** (§9)
>
> As demais seções dão contexto e análise de suporte.

---

## 1. Especificação do problema

Projetar um sistema de controle ativo de vibrações para uma estrutura mecânica modelada como um sistema massa-mola-amortecedor de um grau de liberdade (SDOF), submetida a excitação harmônica externa.

A força de controle é aplicada por um atuador genérico (em estrutura real seria um atuador hidráulico, eletromagnético ou piezoelétrico) e é determinada por um controlador fuzzy Mamdani.

## 2. Variáveis e dimensionamento

### Parâmetros da planta

| Símbolo    | Valor              | Descrição                                          |
| ---------- | ------------------ | -------------------------------------------------- |
| $m$        | $1{,}0$ kg         | Massa                                              |
| $k$        | $100$ N/m          | Rigidez da mola                                    |
| $\zeta$    | $0{,}02$           | Razão de amortecimento (estrutura levemente amortecida) |
| $c$        | $0{,}4$ N·s/m      | $c = 2\zeta\sqrt{km}$                              |
| $\omega_n$ | $10$ rad/s         | Frequência natural não amortecida ($\sqrt{k/m}$)   |
| $f_n$      | $\approx 1{,}59$ Hz | Frequência natural em Hz                          |
| $F_0$      | $1{,}0$ N          | Amplitude da força de excitação harmônica          |

### Variáveis do controlador

| Tipo     | Variável     | Domínio              | Termos linguísticos        |
| -------- | ------------ | -------------------- | -------------------------- |
| Entrada  | Deslocamento | $[-0{,}3; +0{,}3]$ m | NG, NP, Z, PP, PG          |
| Entrada  | Velocidade   | $[-3; +3]$ m/s       | NG, NP, Z, PP, PG          |
| Saída    | Força        | $[-3; +3]$ N         | NG, NP, Z, PP, PG          |

Os universos de discurso foram escolhidos para abranger a resposta livre próxima da ressonância: a amplitude de regime permanente sem controle no caso ressonante é $x_\text{ss} = F_0 / (c\,\omega_n) \approx 0{,}25$ m, com velocidade de pico $\approx 2{,}5$ m/s. A faixa de força (3 vezes $F_0$) garante autoridade de controle suficiente.

Os termos linguísticos seguem a convenção:

- **NG** — Negativo Grande
- **NP** — Negativo Pequeno
- **Z** — Zero
- **PP** — Positivo Pequeno
- **PG** — Positivo Grande

---

## 3. Tela 1 — Variáveis de entrada

### 3.1 Deslocamento

Cinco funções de pertinência sobre $[-0{,}3; +0{,}3]$ m: dois ombros (NG, PG) e três triangulares (NP, Z, PP), com sobreposição em $\mu = 0{,}5$ entre vizinhas — partição padrão para controlador Mamdani.

![Funções de pertinência — deslocamento](figures/mf_deslocamento.png)

### 3.2 Velocidade

Mesma estrutura, mapeada para $[-3; +3]$ m/s.

![Funções de pertinência — velocidade](figures/mf_velocidade.png)

---

## 4. Tela 2 — Variável de saída

Força de controle sobre $[-3; +3]$ N, com a mesma família de cinco termos. Centróides nominais nos extremos (NG em $-3$ N, PG em $+3$ N) e nos termos intermediários (NP em $-1{,}5$ N, PP em $+1{,}5$ N). O termo Z está centrado em zero, correspondendo à ausência de ação de controle.

![Função de pertinência — força](figures/mf_forca.png)

---

## 5. Tela 3 — Base de regras

A base contém $5 \times 5 = 25$ regras, cobrindo todas as combinações de termos das duas entradas. A linha indica o termo da velocidade; a coluna indica o termo do deslocamento; a célula contém o termo de saída.

| Velocidade \ Deslocamento | NG  | NP  | Z   | PP  | PG  |
| ------------------------- | --- | --- | --- | --- | --- |
| **NG**                    | PG  | PG  | PG  | PP  | Z   |
| **NP**                    | PG  | PP  | PP  | Z   | NP  |
| **Z**                     | PG  | PP  | Z   | NP  | NG  |
| **PP**                    | PP  | Z   | NP  | NP  | NG  |
| **PG**                    | Z   | NP  | NG  | NG  | NG  |

![Mapa de calor da base de regras](figures/rule_base.png)

### 5.1 Lógica da base

A base codifica um controlador estilo *plano de fase* (PD-fuzzy): a força aplicada opõe-se energeticamente à dinâmica.

- **Diagonal principal (NG, NG) → PG** ... **(PG, PG) → NG**: quando deslocamento e velocidade têm o mesmo sinal (massa afastando-se da origem), aplica-se força máxima oposta.
- **Anti-diagonal (NG, PG) → Z** ... **(PG, NG) → Z**: quando deslocamento e velocidade têm sinais opostos (massa retornando à origem), o controlador recua — a dinâmica natural já está corrigindo o estado.
- **Linha/coluna central (Z, ·)** e **(·, Z)**: o controlador atua proporcionalmente à magnitude da entrada não-nula, indo de PG quando o outro for NG, até NG quando o outro for PG.

A simetria é fundamental: não há viés em nenhuma direção da resposta.

---

## 6. Inferência

Mamdani clássico:

- t-norma para AND (entre antecedentes): `min`.
- Implicação de Mamdani: recorte do consequente pela força da regra.
- Agregação inter-regras: `max`.
- Defuzzificação: centróide sobre uma grade discreta de 401 pontos em $[-3; +3]$ N.

Para cada regra $i$:

$$
w_i \;=\; \min\bigl(\mu_{X_i}(x),\; \mu_{V_i}(\dot x)\bigr),
\qquad
\mu_{U_i'}(u) \;=\; \min\bigl(w_i,\; \mu_{U_i}(u)\bigr)
$$

Saída agregada:

$$
\mu_{U'}(u) \;=\; \max_i \mu_{U_i'}(u)
$$

Saída crisp por centróide:

$$
u^* \;=\; \frac{\sum_u u \cdot \mu_{U'}(u)}{\sum_u \mu_{U'}(u)}
$$

---

## 7. Superfície de controle

Avaliando o FIS sobre a grade $[-0{,}3; 0{,}3]\,\mathrm{m} \times [-3; 3]\,\mathrm{m/s}$:

![Superfície de controle](figures/control_surface.png)

A superfície é suave (graças à sobreposição dos termos e ao centróide) e **anti-simétrica em torno da origem** — propriedade desejável para um controlador de vibração: a resposta é a mesma em magnitude para deslocamentos opostos, apenas com o sinal trocado.

---

## 8. Modelo da planta e simulação

Equação do movimento:

$$
m\,\ddot x(t) + c\,\dot x(t) + k\,x(t) \;=\; F_\text{ext}(t) + u(t)
$$

com $F_\text{ext}(t) = F_0\sin(\omega t)$ e $u(t) = \mathrm{FIS}(x(t),\,\dot x(t))$ realimentada do estado da planta.

A integração numérica usa Runge-Kutta de 4ª ordem com passo $\Delta t = 5$ ms e *zero-order hold* sobre $u$ — isto é, a saída do controlador é mantida constante ao longo de cada passo de integração, modelando o comportamento de um atuador real comandado em tempo discreto.

---

## 9. Tela 4 — Exemplo de aplicação do sistema de controle

Excitação harmônica em ressonância ($\omega = \omega_n = 10$ rad/s) — o caso mais severo. Sistema parte do repouso, $x(0) = \dot x(0) = 0$.

![Exemplo de aplicação — simulação no domínio do tempo](figures/simulation.png)

### 9.1 Métricas de regime permanente (últimos 4 s)

| Métrica                       | Sem controle | Com controle fuzzy | Redução |
| ----------------------------- | -----------: | -----------------: | ------: |
| Pico $\lvert x \rvert$ (m)    |       0,2270 |             0,0742 |  67,3 % |
| RMS $x$ (m)                   |       0,1532 |             0,0526 |  65,7 % |
| Pico $\lvert u \rvert$ (N)    |            — |             0,7443 |       — |

### 9.2 Interpretação

- O sistema sem controle, levemente amortecido ($\zeta = 0{,}02$) e em ressonância, alcança grande amplitude — quase 23 cm de oscilação em torno da posição de equilíbrio.
- Com o controlador fuzzy ativo, a amplitude de regime cai para aproximadamente **um terço** do valor sem controle.
- A força de controle de pico ($\approx 0{,}74$ N) é da mesma ordem da força de excitação ($F_0 = 1$ N) e bem abaixo do limite do atuador ($U_\text{max} = 3$ N) — há ainda margem para ajuste mais agressivo.
- A força $u(t)$ está praticamente em oposição de fase com $F_\text{ext}(t)$, como esperado para um cancelamento ativo: ao detectar a tendência de movimento, o controlador aplica uma força contrária na hora certa.

---

## 10. Resposta em frequência

Varredura entre $0{,}4\,\omega_n$ e $1{,}8\,\omega_n$, registrando a amplitude de regime permanente em cada caso:

![Resposta em frequência](figures/frequency_response.png)

- **Pico de ressonância**: o controlador reduz drasticamente a amplitude em $\omega \approx \omega_n$, achatando o pico ressonante.
- **Fora da ressonância**: a contribuição do controlador é pequena (a planta já é estável e o controlador, vendo deslocamento e velocidade pequenos, comanda força próxima de zero).
- **Acima de $1{,}3\,\omega_n$**: as duas curvas praticamente coincidem — em altas frequências a planta atenua naturalmente a excitação, e a ação fuzzy é mínima.

Este é o padrão típico de um controle ativo de vibrações: maior benefício no entorno da ressonância, sem perturbar regiões já bem comportadas.

---

## 11. Conclusões

- O controlador Mamdani projetado **funciona**: redução de ~67 % na amplitude de pico e RMS em ressonância, com força de controle de pico bem abaixo do limite do atuador.
- A estrutura *plano-de-fase* da base de regras é equivalente a um controlador PD não-linear, mas com a vantagem da **interpretabilidade**: cada célula da tabela 5 × 5 é justificável a partir do conhecimento de especialista.
- A **superfície de controle anti-simétrica** garante resposta uniforme em ambas as direções; a suavização introduzida pelo centróide evita comportamento *bang-bang*.
- A redução de amplitude poderia ser melhorada por:
  1. **Mais termos linguísticos** (7 ou 9 termos por variável) — refinaria a resolução do controlador.
  2. **Ajuste dos ganhos de escala** das entradas e saída — possivelmente via algoritmo genético, conforme literatura.
  3. **Atuador mais rápido** — neste exercício o controlador usa *zero-order hold* a 5 ms, próximo de uma implementação real.
  4. **Universo de força mais largo** — aumentar $U_\text{max}$ daria mais autoridade.
- A escolha entre Mamdani e Sugeno favoreceu Mamdani aqui pela clareza pedagógica: cada regra é uma frase em português, e a simetria física do problema (um controlador de oscilação não pode ter viés direcional) emerge naturalmente da simetria do mapa de regras.

---

## 12. Como executar

A partir da raiz do repositório:

```bash
python exercises/exercicio2_sdof_vibration_control/sdof_vibration.py
```

A execução gera as sete figuras em `figures/` e imprime as métricas de regime no terminal.
