# Pokémon Coach — full QA log

Complete turn-by-turn record of the adversarial testing run against the `pokemon-coach` branch. Every question asked, every answer returned verbatim, and the ground truth each answer was checked against.

- **Target**: live `/api/coach` on `http://127.0.0.1:5003`, plus `/coach` in headless Chromium
- **Date**: 2026-08-31
- **Ground truth**: PokéAPI damage relations (18×18 chart via `eval_harness.typechart`) and PokéAPI `/pokemon-species` → `/evolution-chain`
- **Graded by**: `eval_harness.grading.grade_turn` for the battle battery; hand-checked against the chart for everything else

> **Caveat.** Coveo RGA is non-deterministic. Exact answer wording will differ on a re-run. The structural results — abstention behaviour, retrieval budget, grader coverage gaps, comparison overfire, and all chart arithmetic — are deterministic and were re-verified.

## Contents

| Part | Suite | Turns |
|---|---|---|
| 1 | Wild-encounter battle battery | 35 |
| 2 | Player-intent battery | 30 |
| 3 | Multi-turn journeys | 17 |
| 4 | Pure-function fuzzing | 26 assertions |
| 5 | Protocol & abuse | 16 payloads + 5 probes |
| 6 | Conversation state (in-process) | 5 probes |
| 7 | Retrieval isolation A/B | 2 arms + 2 queries |
| 8 | Browser (headless Chromium) | 9 probes |
| 9 | Aggregates and cross-suite tables | — |
| A | Scripts and reproduction | — |

---

## Part 1 — Wild-encounter battle battery

Seven scenarios drawn by `eval_harness.ScenarioBuilder` (seed 20260831), one per axis, five probes each in a single session. The axis names the property the scenario was *constructed* to have, so each one tests a specific failure mode.

Probe sequence per scenario:

1. `lookup` — *Tell me about {wild}.*
2. `advantage` — *My team is {six names}. Which of them has a type advantage against {wild}?*
3. `avoid` — *Which of those would be a bad idea to send out?*
4. `pronoun` — *What type is it weak to?*
5. `unnamed_team` — *Given all that, who should I lead with?*

Verdicts come from `grade_turn`: `correct` | `partial` | `wrong` | `abstained` | `error`. **harmful** marks a recommended teammate that mathematically cannot win.

### S1 · axis `baseline` · wild **Pancham** (fighting)

| Team member | Typing |
|---|---|
| Marshadow | fighting/ghost |
| Gulpin | poison |
| Electabuzz | electric |
| Grookey | grass |
| Xatu | psychic/flying |
| Jirachi | steel/psychic |

**Ground truth** — has a type advantage: `['Xatu', 'Jirachi']` · liabilities: `none`

#### S1.lookup — `correct` · 8.94s

**Q.** Tell me about Pancham.

**A.**
> Pancham is a Fighting-type Pokémon introduced in Generation 6. It has a leaf in its mouth, which it chews to appear intimidating, though it often ends up smiling instead. Pancham evolves into Pangoro at level 32 when a Dark-type Pokémon is in the party. It has a base Friendship of 70 in Generations 6-7. Pancham can learn moves like Leer, Tackle, Taunt, Brick Break, and more through leveling up. It can also learn moves via Technical Machines (TMs) and Technical Records (TRs) in different generations. Pancham's abilities include Iron Fist and Mold Breaker, with Scrappy as a hidden ability.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S1.advantage — `wrong` · 6.89s

**Q.** My team is Marshadow, Gulpin, Electabuzz, Grookey, Xatu and Jirachi. Which of them has a type advantage against Pancham so it can be beaten easily?

**A.**
> Pancham is a Fighting-type Pokémon introduced in Generation 6. It has a leaf in its mouth, which it chews to appear intimidating, though it often ends up smiling instead. Pancham evolves into Pangoro at level 32. It has a base Friendship value of 50 and can be found in various locations, including Route 5 in X and Y, Route 10 and 11 in Sun and Moon, and Route 3 in Sword and Shield. Pancham's signature move is Iron Fist, and it can learn moves like Iron Head, Stone Edge, and Grass Knot.

- expected `['Xatu', 'Jirachi']` · predicted `none`
- missed: `['Jirachi', 'Xatu']`
- retrieval hit (wild's page cited): `True`
- citations: ['Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S1.avoid — `correct` · 2.87s

**Q.** Which of those would be a bad idea to send out?

**A.**
> Pancham is a Fighting-type Pokémon introduced in Generation 6. It has a leaf in its mouth, which it chews to appear intimidating, though it often ends up smiling instead. Pancham evolves into Pangoro at level 32. It has a base Friendship value of 50 and can be found in various locations, such as Route 5 in X/Y, Route 10 and 11 in Sun/Moon, and Route 3 in Sword/Shield. Pancham's signature move is Iron Fist, and it can learn moves like Iron Head, Stone Edge, and Grass Knot.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S1.pronoun — `partial` · 2.4s

**Q.** What type is it weak to?

**A.**
> Pancham is a Fighting-type Pokémon. To defeat it easily, you need a Pokémon with a type advantage. Among your team, Xatu (Psychic/Flying) has a type advantage against Pancham. Psychic-type moves are super effective against Fighting-type Pokémon.

- expected `['Xatu', 'Jirachi']` · predicted `['Xatu']`
- missed: `['Jirachi']`
- retrieval hit (wild's page cited): `True`
- citations: ['Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S1.unnamed_team — `wrong` · 2.98s

**Q.** Given all that, who should I lead with?

**A.**
> Pancham is a Fighting-type Pokémon that evolves into Pangoro, a Fighting/Dark type Pokémon. Pangoro's dual typing makes it more versatile in battles, but Pancham's single Fighting type could be a disadvantage in certain situations. Therefore, sending out Pancham without evolving it could be a bad idea, especially against opponents with strong Dark or Ground-type moves.

- expected `['Xatu', 'Jirachi']` · predicted `none`
- missed: `['Jirachi', 'Xatu']`
- retrieval hit (wild's page cited): `True`
- citations: ['Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pancham Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Pangoro Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

---

### S2 · axis `dual_type` · wild **Kabuto** (rock/water)

| Team member | Typing |
|---|---|
| Sandaconda | ground |
| Carbink | rock/fairy |
| Cranidos | rock |
| Floatzel | water |
| Geodude | rock/ground |
| Haxorus | dragon |

**Ground truth** — has a type advantage: `['Sandaconda', 'Geodude']` · liabilities: `['Sandaconda', 'Carbink', 'Cranidos', 'Geodude']`

#### S2.lookup — `correct` · 5.36s

**Q.** Tell me about Kabuto.

**A.**
> Kabuto is a Rock/Water type Pokémon introduced in Generation 1. It is a Shellfish Pokémon, resembling an ancient helmet used by Japanese warriors. Kabuto can be obtained by reviving the Dome Fossil. It evolves into Kabutops at level 40. Kabuto has a base experience yield of 119 in Generations 1-3 and 99 in Generation 4. It has a base Friendship value of 70 in Generations 2-7. Kabuto's base stats include HP 30, Attack 80, Defense 90, Special Attack 55, Special Defense 45, and Speed 55. It has abilities like Swift Swim and Battle Armor, with Weak Armor as a hidden ability. Kabuto can be found in various locations across different games, including Cinnabar Island, Oreburgh City, and Roaring-Sea Caves.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabutops Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S2.advantage — `wrong` · 4.67s

**Q.** My team is Sandaconda, Carbink, Cranidos, Floatzel, Geodude and Haxorus. Which of them has a type advantage against Kabuto so it can be beaten easily?

**A.**
> Kabuto is a Rock/Water type Pokémon introduced in Generation 1. It is a Shellfish Pokémon that resembles an ancient helmet used by Japanese warriors. Kabuto can be obtained by reviving the Dome Fossil. It evolves into Kabutops at level 40. Kabuto has a base Friendship of 50, a catch rate of 45, and a base experience yield of 119 in Generations 1-3, and 99 in Generation 4. Its base stats include HP 30, Attack 80, Defense 90, Special Attack 55, Special Defense 45, and Speed 55. Kabuto's abilities are Swift Swim and Battle Armor, with Weak Armor as a hidden ability.

- expected `['Sandaconda', 'Geodude']` · predicted `none`
- missed: `['Geodude', 'Sandaconda']`
- retrieval hit (wild's page cited): `True`
- citations: ['Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S2.avoid — `wrong` · 3.44s

**Q.** Which of those would be a bad idea to send out?

**A.**
> Kabuto is a Rock/Water type Pokémon from Generation 1, resembling an ancient Japanese warrior's helmet. It evolves into Kabutops at level 40. Kabuto can be obtained by reviving the Dome Fossil. It has a base Friendship of 50, a catch rate of 45, and provides 71 base experience. Kabuto's base stats include HP 30, Attack 80, Defense 90, Special Attack 55, Special Defense 45, and Speed 55. Kabutops, its evolved form, has higher stats and can be obtained by evolving Kabuto. Kabutops has a base Friendship of 70, a catch rate of 45, and provides 173 base experience. Its base stats include HP 60, Attack 115, Defense 105, Special Attack 65, Special Defense 70, and Speed 80.

- expected `['Sandaconda', 'Carbink', 'Cranidos', 'Geodude']` · predicted `none`
- missed: `['Carbink', 'Cranidos', 'Geodude', 'Sandaconda']`
- retrieval hit (wild's page cited): `True`
- citations: ['Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabutops Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabutops Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S2.pronoun — `wrong` · 2.27s

**Q.** What type is it weak to?

**A.**
> Kabuto is a Rock/Water type Pokémon. Among your team, Floatzel, with its Water/Flying typing, has a type advantage against Kabuto, making it easier to defeat. Floatzel's Water-type moves will be super effective against Kabuto.

- expected `['Sandaconda', 'Geodude']` · predicted `['Floatzel']`
- missed: `['Geodude', 'Sandaconda']`
- false positives: `['Floatzel']`
- retrieval hit (wild's page cited): `True`
- citations: ['Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S2.unnamed_team — `wrong` · 2.36s

**Q.** Given all that, who should I lead with?

**A.**
> Kabuto is a Rock/Water type Pokémon. It evolves into Kabutops at level 40. Kabuto can be obtained by reviving the Dome Fossil.

- expected `['Sandaconda', 'Geodude']` · predicted `none`
- missed: `['Geodude', 'Sandaconda']`
- retrieval hit (wild's page cited): `True`
- citations: ['Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Kabuto Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

---

### S3 · axis `four_x_defence` · wild **Oddish** (grass/poison)

| Team member | Typing |
|---|---|
| Chespin | grass |
| Mienshao | fighting |
| Grookey | grass |
| Piloswine | ice/ground |
| Kabutops | rock/water |
| Gliscor | ground/flying |

**Ground truth** — has a type advantage: `none` · liabilities: `none`

#### S3.lookup — `correct` · 2.68s

**Q.** Tell me about Oddish.

**A.**
> Oddish is a Grass/Poison type Pokémon introduced in Generation 1. It is known as the Weed Pokémon and has a height of 0.5 meters and a weight of 5.4 kg. Oddish has abilities like Chlorophyll and Run Away (hidden). It evolves into Gloom at level 21 and further into Vileplume using a Sun Stone. Oddish has a base Special stat of 75 and a base experience yield of 78 in Generations 1-4. It has a base Friendship value of 70 in Generations 2-7. Oddish is known for burying itself in the ground during the day and roaming at night to scatter its seeds. It can be mistaken for a clump of weeds and shrieks if pulled out of the ground.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Oddish Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Oddish Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S3.advantage — `abstained` · 0.72s

**Q.** My team is Chespin, Mienshao, Grookey, Piloswine, Kabutops and Gliscor. Which of them has a type advantage against Oddish so it can be beaten easily?

**A.**
> (no answer generated)

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `False`
- citations: `none`
- server grading flags shown to the user: `none`

#### S3.avoid — `abstained` · 4.6s

**Q.** Which of those would be a bad idea to send out?

**A.**
> (no answer generated)

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `False`
- citations: `none`
- server grading flags shown to the user: `none`

#### S3.pronoun — `wrong` · 2.48s

**Q.** What type is it weak to?

**A.**
> Oddish is a Grass/Poison type Pokémon. Among your team, Mienshao (Dark/Fighting), Grookey (Grass), Piloswine (Ice), Kabutops (Rock/Water), and Gliscor (Ground/Flying) have a type advantage against Oddish. Mienshao, Piloswine, Kabutops, and Gliscor can beat Oddish easily. Grookey, being Grass, would be a bad idea to send out against Oddish as it would not have a type advantage.

- expected `['Piloswine', 'Gliscor']` · predicted `['Mienshao', 'Grookey', 'Piloswine', 'Kabutops', 'Gliscor']`
- false positives: `['Grookey', 'Kabutops', 'Mienshao']`
- **harmful**: recommended **Grookey** — takes 2x and hits for only 0.25x
- **harmful**: recommended **Kabutops** — takes 4x and hits for only 1x
- **harmful**: recommended **Mienshao** — takes 1x and hits for only 0.5x
- **type error** (contradiction): "Mienshao (Dark/Fighting)" — claimed `['dark', 'fighting']`, actual `['fighting']`
- **type error** (incomplete): "Piloswine (Ice)" — claimed `['ice']`, actual `['ice', 'ground']`
- retrieval hit (wild's page cited): `True`
- citations: ['Oddish Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Chespin Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Chesnaught Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Chespin Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: [{'message': 'Mienshao', 'quote': 'Mienshao (Dark/Fighting)', 'type': 'type_error'}, {'message': 'Piloswine', 'quote': 'Piloswine (Ice)', 'type': 'type_error'}]

#### S3.unnamed_team — `wrong` · 2.64s

**Q.** Given all that, who should I lead with?

**A.**
> Oddish, a Grass/Poison type Pokémon, is weak to Fire, Ice, Flying, and Psychic types. Among the Pokémon mentioned, Mienshao (Dark/Fighting) and Grookey (Grass) have a type advantage against Oddish. Piloswine (Ice) and Kabutops (Rock/Water) also have a type advantage due to Ice and Rock types being effective against Grass. Gliscor (Ground/Flying) has a type advantage due to Flying type. Therefore, sending out Grookey, Piloswine, Kabutops, or Gliscor would be a good idea against Oddish.

- expected `['Piloswine', 'Gliscor']` · predicted `['Mienshao', 'Grookey', 'Piloswine', 'Kabutops', 'Gliscor']`
- false positives: `['Grookey', 'Kabutops', 'Mienshao']`
- **harmful**: recommended **Grookey** — takes 2x and hits for only 0.25x
- **harmful**: recommended **Kabutops** — takes 4x and hits for only 1x
- **harmful**: recommended **Mienshao** — takes 1x and hits for only 0.5x
- **type error** (contradiction): "Mienshao (Dark/Fighting)" — claimed `['dark', 'fighting']`, actual `['fighting']`
- **type error** (incomplete): "Piloswine (Ice)" — claimed `['ice']`, actual `['ice', 'ground']`
- retrieval hit (wild's page cited): `True`
- citations: ['Oddish Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Oddish Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: [{'message': 'Mienshao', 'quote': 'Mienshao (Dark/Fighting)', 'type': 'type_error'}, {'message': 'Piloswine', 'quote': 'Piloswine (Ice)', 'type': 'type_error'}]

---

### S4 · axis `zero_damage` · wild **Toucannon** (normal/flying)

| Team member | Typing |
|---|---|
| Venipede | bug/poison |
| Solosis | psychic |
| Iron Treads | ground/steel |
| Sawk | fighting |
| Carkol | rock/fire |
| Gothita | psychic |

**Ground truth** — has a type advantage: `['Carkol']` · liabilities: `['Venipede', 'Sawk']`

#### S4.lookup — `correct` · 2.89s

**Q.** Tell me about Toucannon.

**A.**
> Toucannon is a Normal/Flying type Pokémon introduced in Generation 7. It evolves from Trumbeak at level 28. Toucannon stands at 1.1 meters tall and weighs 26.0 kg. It has a base Friendship of 70 and a base experience yield of 218. Toucannon's abilities include Keen Eye, Skill Link, and Sheer Force (hidden). It has a Catch rate of 45 and belongs to the Flying Egg Group. Toucannon's base stats are HP 80, Attack 120, Defense 75, Special Attack 75, Special Defense 75, and Speed 60. It can learn moves like Hurricane, Hyper Beam, Brave Bird, and others through leveling up or TMs. Toucannon is found in Sun, Moon, Ultra Sun, and Ultra Moon.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S4.advantage — `wrong` · 5.51s

**Q.** My team is Venipede, Solosis, Iron Treads, Sawk, Carkol and Gothita. Which of them has a type advantage against Toucannon so it can be beaten easily?

**A.**
> Toucannon is a Normal/Flying type Pokémon introduced in Generation 7, evolving from Trumbeak at level 28. It stands 1.1 meters tall and weighs 26.0 kg. Toucannon has a base Friendship of 70 and can have abilities like Keen Eye, Skill Link, and Sheer Force (hidden). It has a Catch rate of 45 and a Medium Fast growth rate. Toucannon's base stats include HP 80, Attack 120, Defense 75, Sp. Atk 75, Sp. Def 75, and Speed 60. It learns moves like Echoed Voice, Peck, Rock Blast, and Drill Peck. Toucannon can be found in locations like Route 11, Poni Grove, and Poni Plains.

- expected `['Carkol']` · predicted `none`
- missed: `['Carkol']`
- retrieval hit (wild's page cited): `True`
- citations: ['Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S4.avoid — `wrong` · 5.49s

**Q.** Which of those would be a bad idea to send out?

**A.**
> Toucannon is a Normal/Flying type Pokémon introduced in Generation 7, evolving from Trumbeak at level 28. It stands 1.1 meters tall and weighs 26.0 kg. Toucannon has a base Friendship of 70 and can have abilities like Keen Eye, Skill Link, and Sheer Force (hidden). It has a Catch rate of 45 and a Medium Fast growth rate. Toucannon's base stats include HP 80, Attack 120, Defense 75, Sp. Atk 75, Sp. Def 75, and Speed 60. It learns moves like Echoed Voice, Peck, Rock Blast, and Drill Peck. Toucannon can be found in locations like Route 11, Poni Grove, and Poni Plains.

- expected `['Venipede', 'Sawk']` · predicted `none`
- missed: `['Sawk', 'Venipede']`
- retrieval hit (wild's page cited): `True`
- citations: ['Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S4.pronoun — `wrong` · 3.9s

**Q.** What type is it weak to?

**A.**
> Toucannon is a Normal/Flying type Pokémon. Among your team, only Iron Treads, a Steel type, has a type advantage against Toucannon, making it easier to defeat. Iron Treads' Steel attacks are super effective against Toucannon's Normal type.

- expected `['Carkol']` · predicted `['Iron Treads']`
- missed: `['Carkol']`
- false positives: `['Iron Treads']`
- **harmful**: recommended **Iron Treads** — has a ground STAB that deals 0x
- retrieval hit (wild's page cited): `True`
- citations: ['Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S4.unnamed_team — `wrong` · 5.58s

**Q.** Given all that, who should I lead with?

**A.**
> Toucannon, a Normal/Flying type Pokémon, is not recommended for battle in Pokémon Legends: Z-A as it does not learn any moves through leveling up or TMs in this game. Its abilities include Keen Eye, Skill Link, and Sheer Force (hidden). Toucannon evolves from Trumbeak at level 28 and has a base Friendship of 70. It stands 1.1 meters tall and weighs 26.0 kg.

- expected `['Carkol']` · predicted `none`
- missed: `['Carkol']`
- retrieval hit (wild's page cited): `True`
- citations: ['Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

---

### S5 · axis `no_advantage` · wild **Klang** (steel)

| Team member | Typing |
|---|---|
| Lugia | psychic/flying |
| Tropius | grass/flying |
| Floatzel | water |
| Liepard | dark |
| Castform | normal |
| Latias | dragon/psychic |

**Ground truth** — has a type advantage: `none` · liabilities: `['Lugia', 'Tropius', 'Castform', 'Latias']`

#### S5.lookup — `correct` · 4.39s

**Q.** Tell me about Klang.

**A.**
> Klang is a Steel-type Pokémon introduced in Generation 5. It evolves from Klink at level 49. Klang is known as the Gear Pokémon and has a body composed of a minigear and a big gear. It communicates through its rotation speed, spinning faster when angry. In Pokémon Sword and Shield, Klang can be found on Route 10, Dusty Bowl. It has a base Friendship of 50 and a Medium Slow growth rate. Klang's abilities include Plus, Minus, and Clear Body (hidden). It has a total base stat of 440.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S5.advantage — `correct` · 5.38s

**Q.** My team is Lugia, Tropius, Floatzel, Liepard, Castform and Latias. Which of them has a type advantage against Klang so it can be beaten easily?

**A.**
> Klang is a Steel-type Pokémon introduced in Generation 5, evolving from Klink at level 49. Known as the Gear Pokémon, it has a body made of a minigear and a big gear. Klang communicates its feelings by changing its rotation direction, rotating faster when angry. It is dangerous if the minigear it launches doesn't return. In Generations 5-7, Klang has a base Friendship value of 70. It has a base stat total of 440 and can learn moves like Bind. In Pokémon Legends: Z-A, Klang does not learn any level-up moves or TM moves.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S5.avoid — `wrong` · 4.82s

**Q.** Which of those would be a bad idea to send out?

**A.**
> Klang is a Steel-type Pokémon introduced in Generation 5, evolving from Klink at level 49. Known as the Gear Pokémon, it has a body made of a minigear and a big gear. Klang communicates its feelings by changing its rotation direction, rotating faster when angry. It is dangerous if the minigear it launches doesn't return. In Generations 5-7, Klang has a base Friendship value of 70. It has a base stat total of 440, with 60 HP, 80 Attack, 95 Defense, 70 Special Attack, 85 Special Defense, and 50 Speed. Klang's abilities include Plus, Minus, and Clear Body (hidden). It belongs to the Mineral Egg Group and is genderless.

- expected `['Lugia', 'Tropius', 'Castform', 'Latias']` · predicted `none`
- missed: `['Castform', 'Latias', 'Lugia', 'Tropius']`
- retrieval hit (wild's page cited): `True`
- citations: ['Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klink Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S5.pronoun — `wrong` · 2.63s

**Q.** What type is it weak to?

**A.**
> Klang, a Steel-type Pokémon, is weak to Fire, Fighting, and Ground-type moves. Among your team members, Castform (in its Fire-type form) and Tropius have a type advantage against Klang. Castform (Fire) can deal super-effective damage, while Tropius, with its Grass-type moves, can also effectively attack Klang.

- expected `n/a` · predicted `['Tropius', 'Castform']`
- false positives: `['Castform', 'Tropius']`
- **harmful**: recommended **Castform** — takes 1x and hits for only 0.5x
- **harmful**: recommended **Tropius** — takes 1x and hits for only 0.5x
- **type error** (contradiction): "Castform (Fire)" — claimed `['fire']`, actual `['normal']`
- retrieval hit (wild's page cited): `True`
- citations: ['Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klink Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: [{'message': 'Castform', 'quote': 'Castform (Fire)', 'type': 'type_error'}]
- grader notes: ['no teammate has a type advantage, but 2 were claimed to']

#### S5.unnamed_team — `correct` · 2.88s

**Q.** Given all that, who should I lead with?

**A.**
> Klang, a Steel-type Pokémon, evolves from Klink at level 49. It is known as the Gear Pokémon, with a body composed of a minigear and a big gear. Klang communicates its feelings by changing its rotation direction, rotating faster when angry. However, if the minigear it launches doesn't return, it will die. In Pokémon Legends: Z-A, Klang does not learn any level-up moves. Therefore, sending Klang into battle without a proper moveset could be a bad idea.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klang Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Klink Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

---

### S6 · axis `immune_wall` · wild **Solosis** (psychic)

| Team member | Typing |
|---|---|
| Crabominable | fighting/ice |
| Roaring Moon | dragon/dark |
| Manaphy | water |
| Braixen | fire |
| Coalossal | rock/fire |
| Ninjask | bug/flying |

**Ground truth** — has a type advantage: `['Roaring Moon', 'Ninjask']` · liabilities: `['Crabominable']`

#### S6.lookup — `correct` · 2.81s

**Q.** Tell me about Solosis.

**A.**
> Solosis is a Psychic-type Pokémon introduced in Generation 5. It evolves into Duosion at level 32 and into Reuniclus at level 41. Solosis has a base Friendship of 50, but in Generations 5-7, it has a base Friendship of 70. It can be found in various locations across different games, such as Route 5 and 16 in Black and White, and Reflection Cave in X and Y. Solosis has abilities like Overcoat and Magic Guard, with Regenerator as a hidden ability. It can learn moves like Confusion and Protect through leveling up. Solosis is known for its special liquid-covered body, which allows it to survive in any environment.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S6.advantage — `wrong` · 9.04s

**Q.** My team is Crabominable, Roaring Moon, Manaphy, Braixen, Coalossal and Ninjask. Which of them has a type advantage against Solosis so it can be beaten easily?

**A.**
> Solosis is a Psychic-type Pokémon introduced in Generation 5. It evolves into Duosion at level 32 and then into Reuniclus at level 41. Solosis has a base Friendship of 50, but in Generations 5-7, it has a base Friendship of 70. It has abilities like Overcoat and Magic Guard, with Regenerator as a hidden ability. Solosis can be found in various locations across different games, such as Route 5 and 16 in Pokémon Black and White, and through trade or migration in others.

- expected `['Roaring Moon', 'Ninjask']` · predicted `none`
- missed: `['Ninjask', 'Roaring Moon']`
- retrieval hit (wild's page cited): `True`
- citations: ['Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Reuniclus Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Duosion Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S6.avoid — `wrong` · 4.14s

**Q.** Which of those would be a bad idea to send out?

**A.**
> Solosis is a Psychic-type Pokémon introduced in Generation 5. It evolves into Duosion at level 32 and then into Reuniclus at level 41. Solosis has a base Friendship of 50, but in Generations 5-7, it has a base Friendship of 70. It has abilities like Overcoat, Magic Guard, and Regenerator (hidden). Solosis can be found in various locations across different games, such as Route 5 and 16 in Pokémon Black and White, and through trade or migration in other games.

- expected `['Crabominable']` · predicted `none`
- missed: `['Crabominable']`
- retrieval hit (wild's page cited): `True`
- citations: ['Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S6.pronoun — `wrong` · 2.58s

**Q.** What type is it weak to?

**A.**
> Solosis is a Psychic-type Pokémon. Among your team, Braixen, a Fire-type Pokémon, has a type advantage against Solosis. Solosis evolves into Duosion at level 32 and then into Reuniclus at level 41.

- expected `['Roaring Moon', 'Ninjask']` · predicted `['Braixen']`
- missed: `['Ninjask', 'Roaring Moon']`
- false positives: `['Braixen']`
- retrieval hit (wild's page cited): `True`
- citations: ['Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Duosion Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S6.unnamed_team — `wrong` · 3.03s

**Q.** Given all that, who should I lead with?

**A.**
> Solosis, a Psychic-type Pokémon, evolves into Duosion at level 32 and then into Reuniclus at level 41. While it has a base Friendship of 50, in Generations 5-7, Solosis has a base Friendship value of 70. Given its relatively low base stats and the availability of stronger Pokémon, sending Solosis into battle could be a bad idea. Its low HP, Attack, and Defense stats make it vulnerable in combat.

- expected `['Roaring Moon', 'Ninjask']` · predicted `none`
- missed: `['Ninjask', 'Roaring Moon']`
- retrieval hit (wild's page cited): `True`
- citations: ['Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Reuniclus Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Duosion Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

---

### S7 · axis `four_x_offence` · wild **Breloom** (grass/fighting)

| Team member | Typing |
|---|---|
| Altaria | dragon/flying |
| Flutter Mane | ghost/fairy |
| Butterfree | bug/flying |
| Floatzel | water |
| Scizor | bug/steel |
| Tyrogue | fighting |

**Ground truth** — has a type advantage: `['Altaria', 'Flutter Mane', 'Butterfree']` · liabilities: `['Floatzel']`

#### S7.lookup — `correct` · 4.21s

**Q.** Tell me about Breloom.

**A.**
> Breloom is a Grass/Fighting type Pokémon introduced in Generation 3. It evolves from Shroomish at level 23. Breloom is known for its mushroom-like head and its fighting prowess, which is compared to that of professional boxers. It has a base Friendship of 50 and a fluctuating growth rate. Breloom's abilities include Effect Spore and Poison Heal, with Technician as its hidden ability. It has a base experience yield of 161 and a catch rate of 90. Breloom's signature moves include Scatter, which scatters poisonous spores, and Close Combat, a powerful punch. It is found in various locations across different generations, often through evolution or trade.

- expected `n/a` · predicted `none`
- retrieval hit (wild's page cited): `True`
- citations: ['Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S7.advantage — `wrong` · 2.87s

**Q.** My team is Altaria, Flutter Mane, Butterfree, Floatzel, Scizor and Tyrogue. Which of them has a type advantage against Breloom so it can be beaten easily?

**A.**
> Breloom is a Grass/Fighting type Pokémon introduced in Generation 3, evolving from Shroomish at level 23. It has a mushroom-like head and is known for its fighting technique, likened to that of professional boxers. Breloom's abilities include Effect Spore and Poison Heal, with Technician as its hidden ability. It has a base Friendship of 50 and a base experience yield of 161. Breloom's stats include HP 60, Attack 130, Defense 80, Special Attack 60, Special Defense 60, and Speed 70. It can learn moves like Reversal, Sludge Bomb, Stone Edge, Giga Impact, and Focus Blast. Breloom is a good addition to a team for its diverse moveset and balanced stats.

- expected `['Altaria', 'Flutter Mane', 'Butterfree']` · predicted `none`
- missed: `['Altaria', 'Butterfree', 'Flutter Mane']`
- retrieval hit (wild's page cited): `True`
- citations: ['Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S7.avoid — `wrong` · 2.78s

**Q.** Which of those would be a bad idea to send out?

**A.**
> Breloom is a Grass/Fighting type Pokémon introduced in Generation 3, evolving from Shroomish at level 23. It is recognized for its mushroom-like head and formidable fighting skills, likened to professional boxers. Breloom's abilities include Effect Spore, Poison Heal, and Technician. It has a base Friendship of 50 and a base experience yield of 161. Breloom's strengths include its high Attack stat and diverse moveset, making it a valuable addition to a team.

- expected `['Floatzel']` · predicted `none`
- missed: `['Floatzel']`
- retrieval hit (wild's page cited): `True`
- citations: ['Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Shroomish Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S7.pronoun — `wrong` · 2.61s

**Q.** What type is it weak to?

**A.**
> Altaria, a Dragon/Flying type, has a type advantage against Breloom, a Grass/Fighting type. Altaria's Dragon-type moves will be super effective against Breloom. Additionally, Flying-type moves will also be effective. Butterfree, a Bug/Flying type, and Floatzel, a Water/Steel type, also have type advantages against Breloom.

- expected `['Altaria', 'Flutter Mane', 'Butterfree']` · predicted `['Altaria', 'Butterfree', 'Floatzel']`
- missed: `['Flutter Mane']`
- false positives: `['Floatzel']`
- **harmful**: recommended **Floatzel** — takes 2x and hits for only 0.5x
- retrieval hit (wild's page cited): `True`
- citations: ['Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Altaria Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

#### S7.unnamed_team — `wrong` · 2.69s

**Q.** Given all that, who should I lead with?

**A.**
> Breloom is a Grass/Fighting type Pokémon. It is weak to Flying, Psychic, Bug, Rock, Ghost, and Dark type moves. It has resistances against Water, Electric, Grass, Ice, and Fighting types. Given its weaknesses, sending Breloom against Flying, Psychic, Bug, Rock, Ghost, or Dark type Pokémon would be a bad idea.

- expected `['Altaria', 'Flutter Mane', 'Butterfree']` · predicted `none`
- missed: `['Altaria', 'Butterfree', 'Flutter Mane']`
- retrieval hit (wild's page cited): `True`
- citations: ['Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Breloom Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags shown to the user: `none`

---

## Part 2 — Player-intent battery

Thirty one-shot questions across six themes a real player cares about. Each in its own fresh session, so there is no conversational carry-over. Evolution answers are checked against PokéAPI chains; matchup claims against the chart.

Classification (`classify()` in `g1_gamer.py`, keyword heuristic — the factual verdicts below it were checked by hand):

- `abstained` — matched `eval_harness.grading.is_abstention`; the player sees `(no answer generated)` or an RGA-did-not-trigger fallback
- `dex-dump` — 3+ Pokédex-stat markers and no recommendation language
- `no-advice` — prose, but no recommendation language
- `engaged` — contains a recommendation

### A · Team building

`{'abstained': 3, 'engaged': 2}` over 5 questions

#### `build-around` — abstained · 0.9s

**Q.** Build me a team around my Charizard.

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

#### `cover-gaps` — abstained · 0.9s

**Q.** I've got Charizard, Gyarados and Ferrothorn. What three Pokémon should I add to cover our weaknesses?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

#### `shared-weak` — engaged · 3.6s

**Q.** My whole team is weak to Ground moves. How do I fix that?

**A.**
> To counter a team weak to Ground moves, consider using Pokémon with Rock or Steel typing, as these types are strong against Ground. Additionally, moves like "Rock Slide" (Rock type, 75 power, 90 accuracy) and "Earthquake" (Ground type, 100 power, 100 accuracy) can be effective. Training your Pokémon to learn these moves will help mitigate the weakness to Ground-type attacks.

- citations: ['Sandslash Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `role-request` — engaged · 2.5s

**Q.** What's a good Water-resistant pivot to pair with a Fire-type core?

**A.**
> A good Water-resistant pivot to pair with a Fire-type core is Vaporeon. Vaporeon, a Water-type Pokémon, has resistances to Fire, Ice, Steel, and Electric types, making it an excellent pivot to protect your Fire-type core from Water-type attacks. Its ability, Hydration, restores its HP when it enters battle, adding to its utility in battles.

- citations: ['Vaporeon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Vaporeon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `rate-my-team` — abstained · 2.1s

**Q.** Rate my team: Charizard, Blastoise, Venusaur, Pikachu, Snorlax and Dragonite. What's our biggest hole?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

---

### B · In-battle decisions

`{'abstained': 3, 'engaged': 2}` over 5 questions

#### `best-move` — abstained · 5.8s

**Q.** I'm in a battle. My Charizard is out against a Rhydon. What's the best move here?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

#### `switch-or-not` — abstained · 3.6s · **comparison panel fired**

**Q.** Should I switch or attack? My Gengar is facing a Tyranitar at full HP.

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

#### `who-to-bring` — engaged · 5.3s

**Q.** My opponent just sent out Ferrothorn. I have Charizard, Starmie and Machamp on the bench. Who do I bring in?

**A.**
> To counter Ferrothorn, consider bringing in Machamp. Machamp's Fighting-type moves are super effective against Ferrothorn's Grass-type, making it a strong choice. Starmie, with its Water/Psychic typing, can also be effective, but Machamp's higher Attack stat and better coverage make it the preferred option. Charizard, being a Fire-type, is not as effective against Ferrothorn due to its resistance to Fire.

- **chart error**: `fighting > grass` is actually 1× — "Fighting-type moves are super effective against Ferrothorn's Grass"
- citations: ['Machamp Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Starmie Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Machamp Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: [{'message': 'fighting > grass', 'quote': "Fighting-type moves are super effective against Ferrothorn's Grass", 'type': 'chart_error'}]

#### `hazards` — engaged · 3.8s

**Q.** Is it worth setting up Stealth Rock against a team with three Flying types?

**A.**
> Stealth Rock is a Rock-type move that deals damage to any Pokémon that switches in or uses a move that involves movement. It is particularly effective against Flying types, as they are weak to Rock-type moves. Given that your team has three Flying types, setting up Stealth Rock could be advantageous. Each Flying type that switches in or uses a movement-based move will take damage from Stealth Rock, potentially weakening your opponents. This strategy can be effective if you anticipate your opponents using Flying types in their lineup.

- citations: ['Bombirdier Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Staraptor Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Geodude Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `risk-line` — abstained · 2.0s

**Q.** My Dragonite is at 20% HP against a Weavile. Do I risk Outrage or switch out?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

---

### C · Evolution

`{'no-advice': 5, 'abstained': 1}` over 6 questions

#### `can-evolve` — no-advice · 4.6s

**Q.** Can Starmie evolve?

**A.**
> Starmie evolves from Staryu by using a Water Stone. It does not evolve into another Pokémon.

- **PokéAPI chain**: `['staryu', 'starmie']` · is final form: `True` · evolves into: `nothing`
  - `staryu` → `starmie`: trigger=`use-item` item=`water-stone`
- citations: ['Starmie Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Starmie Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Staryu Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `wrong-stone` — abstained · 0.7s

**Q.** Can I use a Water Stone on Starmie?

**A.**
> (no answer generated)

- **PokéAPI chain**: `['staryu', 'starmie']` · is final form: `True` · evolves into: `nothing`
  - `staryu` → `starmie`: trigger=`use-item` item=`water-stone`
- citations: `none`
- server grading flags: `none`

#### `branch-evo` — no-advice · 6.3s

**Q.** How does Eevee evolve into Umbreon?

**A.**
> To evolve Eevee into Umbreon, you need to expose it to the moon's energy. This can be achieved by leveling up Eevee during nighttime, which is when the rings on its body begin to glow. Alternatively, in Generation 6 and later, you can evolve Eevee into Umbreon by using a Moon Stone. Umbreon is a Dark-type Pokémon known for its rings that glow when it leaps to attack.

- **PokéAPI chain**: `['eevee', 'vaporeon', 'jolteon', 'flareon', 'espeon', 'umbreon', 'leafeon', 'glaceon', 'sylveon']` · is final form: `False` · evolves into: `['vaporeon', 'jolteon', 'flareon', 'espeon', 'umbreon', 'leafeon', 'leafeon', 'leafeon', 'leafeon', 'leafeon', 'leafeon', 'glaceon', 'glaceon', 'glaceon', 'glaceon', 'glaceon', 'glaceon', 'sylveon', 'sylveon']`
  - `eevee` → `vaporeon`: trigger=`use-item` item=`water-stone`
  - `eevee` → `jolteon`: trigger=`use-item` item=`thunder-stone`
  - `eevee` → `flareon`: trigger=`use-item` item=`fire-stone`
  - `eevee` → `espeon`: trigger=`level-up` happiness=`160` time=`day`
  - `eevee` → `umbreon`: trigger=`level-up` happiness=`160` time=`night`
  - `eevee` → `leafeon`: trigger=`level-up`
  - `eevee` → `glaceon`: trigger=`level-up`
  - `eevee` → `sylveon`: trigger=`level-up`
- citations: ['Umbreon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Umbreon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Umbreon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `trade-evo` — no-advice · 2.1s

**Q.** How do I evolve Haunter?

**A.**
> To evolve Haunter, you need to trade it. Haunter evolves into Gengar through trading. This evolution method applies across all generations, from Generation 1 to the latest.

- **PokéAPI chain**: `['gastly', 'haunter', 'gengar']` · is final form: `False` · evolves into: `['gengar']`
  - `gastly` → `haunter`: trigger=`level-up` level=`25`
  - `haunter` → `gengar`: trigger=`trade`
- citations: ['Haunter Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Haunter Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `level-evo` — no-advice · 2.5s

**Q.** What level does Charmeleon evolve at?

**A.**
> Charmeleon evolves from Charmander at level 36. This information is consistent across various generations, as Charmander evolves into Charmeleon at this level in all games.

- **PokéAPI chain**: `['charmander', 'charmeleon', 'charizard']` · is final form: `False` · evolves into: `['charizard']`
  - `charmander` → `charmeleon`: trigger=`level-up` level=`16`
  - `charmeleon` → `charizard`: trigger=`level-up` level=`36`
- citations: ['Charmeleon Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Charmeleon Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `split-evo` — no-advice · 2.3s

**Q.** Does Tyrogue evolve into Hitmonlee or Hitmonchan?

**A.**
> Tyrogue evolves into either Hitmonlee or Hitmonchan based on its Attack and Defense stats at level 20. If Attack is higher, it evolves into Hitmonlee; if Defense is higher, it evolves into Hitmonchan; if they are equal, it evolves into Hitmonchan. This evolution mechanic was introduced in Generation 2.

- **PokéAPI chain**: `['tyrogue', 'hitmonlee', 'hitmonchan', 'hitmontop']` · is final form: `False` · evolves into: `['hitmonlee', 'hitmonchan', 'hitmontop']`
  - `tyrogue` → `hitmonlee`: trigger=`level-up` level=`20`
  - `tyrogue` → `hitmonchan`: trigger=`level-up` level=`20`
  - `tyrogue` → `hitmontop`: trigger=`level-up` level=`20`
- citations: ['Hitmonchan Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Tyrogue Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Hitmonchan Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

---

### D · The rest of the game

`{'abstained': 4, 'no-advice': 2}` over 6 questions

#### `catching` — abstained · 0.7s

**Q.** What's the best Poké Ball to use on a Snorlax at low HP?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

#### `location` — no-advice · 3.4s

**Q.** Where can I find a Dratini?

**A.**
> Dratini can be found in various locations across different Pokémon games. In Red and Blue, it appears in Celadon City and the Safari Zone. In Yellow, it is also available in the Safari Zone. In Gold, Silver, and Crystal, it can be found on Route 45, in Dragon's Den, and Goldenrod City. In Ruby and Sapphire, it requires trading or migrating from another game. In FireRed and LeafGreen, it is available in Celadon City and the Safari Zone. In Emerald, it can be obtained through trading or migrating. In Diamond, Pearl, and Platinum, it is found on Mt. Coronet. In HeartGold and SoulSilver, it appears in Dragon's Den and Goldenrod City. In Black and White, it is located at Dragonspiral Tower. In X and Y, it can be found on Route 21. In Omega Ruby and Alpha Sapphire, it requires trading or migrating. In Sun and Moon, it appears in Poni Gauntlet, Poni Meadow, and Vast Poni Canyon. In Let's Go Pikachu and Let's Go Eevee, it is found on Route 10. In Sword and Shield, it can be found at Ballimere Lake. In Scarlet and Violet, it is available in Casseroya Lake, North Province (Area One), North Province (Area Two), and South Province (Area Six).

- citations: ['Dratini Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Dratini Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Dratini Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `ev-spread` — no-advice · 5.7s

**Q.** What EV spread should I run on Garchomp?

**A.**
> For a Garchomp, an optimal EV spread is 252 Attack, 4 Defense, and 252 Speed. This setup maximizes its Attack and Speed, making it a formidable physical attacker while maintaining some defensive capabilities. The 252 Attack EVs ensure high damage output, while the 252 Speed EVs allow it to outspeed most opponents. The 4 Defense EVs are minimal but provide some resilience against physical attacks. This EV spread is ideal for competitive play, allowing Garchomp to excel in battles.

- citations: ['Garchomp Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Garchomp Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Garchomp Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Garchomp Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `held-item` — abstained · 0.7s

**Q.** What held item is best on a Dragonite?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

#### `ability-choice` — abstained · 1.9s · **comparison panel fired**

**Q.** Is Intimidate or Blaze the better ability on Arcanine?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

#### `shiny` — abstained · 0.6s

**Q.** How do I increase my odds of finding a shiny?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

---

### E · Rare encounter

`{'engaged': 2, 'abstained': 2, 'no-advice': 1}` over 5 questions

#### `rare-plain` — engaged · 3.9s

**Q.** I just found a Feebas in the wild. Is that actually a rare encounter?

**A.**
> Yes, encountering a Feebas in the wild is considered rare. In Ruby, Sapphire, and Emerald, Feebas can only be found by fishing in one of six random squares on Route 119. Similarly, in Diamond, Pearl, and Platinum, it can only be found in one of four random squares in Mt. Coronet. This rarity is due to its limited availability and the need to fish in specific locations.

- citations: ['Feebas Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Feebas Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `rare-or` — engaged · 6.1s

**Q.** Is Chansey actually rare, or does it just feel that way?

**A.**
> Chansey is considered rare due to its elusive nature and difficulty in capturing. Pokédex entries from various generations describe it as rare and elusive, with phrases like "few in number" and "difficult to capture." Despite its rarity, Chansey is known for laying nutritious eggs, which adds to its desirability. Its rarity is further emphasized by the fact that people try to catch it for its eggs, but it is rarely found.

- citations: ['Chansey Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `rare-compare` — abstained · 7.9s

**Q.** How rare is Dratini compared to Magikarp?

**A.**
> (RGA model did not trigger. Top result: Dratini is a Dragon type Pokémon introduced in Generation 1. ... DRATINI continually molts and sloughs off its old skin. ... What happens when you fish up a Dratini in Magikarp Jump?; Magikarp is based on a carp, but it also embodies a popular motif in Chinese ... #0129 Magikarp Water ... Magikarp learns the following moves in Pokémon Legends: Z-A at the levels specified.; This is the complete National Pokédex for Generation 9, which lists every one of the 1025 Pokémon ... Click a Pokémon's name to see its detailed Pokédex page, or click a type to see other ...)

- citations: `none`
- server grading flags: `none`

#### `rare-legendary` — no-advice · 2.2s

**Q.** Is Zapdos a legendary, or just an uncommon bird?

**A.**
> Zapdos is a legendary Pokémon. It is an Electric/Flying type introduced in Generation 1, known for its ability to control electricity and its association with thunderclouds. Various Pokédex entries across different generations describe Zapdos as a legendary bird Pokémon, emphasizing its mythical status and unique abilities.

- citations: ['Zapdos Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Zapdos Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

#### `rare-shiny` — abstained · 0.8s

**Q.** I ran into a red Gyarados. Is that a shiny or a normal encounter?

**A.**
> (no answer generated)

- citations: `none`
- server grading flags: `none`

---

### F · Power user

`{'no-advice': 3}` over 3 questions

#### `team-audit-0` — no-advice · 2.8s

**Q.** Here's my team: Frogadier, Flapple, Snorunt, Latias, Ribombee and Carkol. Identify the type weaknesses in my team.

**A.**
> Frogadier (Water/Grass) is weak to Electric, Grass, and Ice. Flapple (Bug/Fairy) is weak to Fire, Fighting, and Poison. Snorunt (Ice) is weak to Fire, Fighting, Rock, and Steel. Latias (Dragon/Psychic) is weak to Dark, Ghost, and Ice. Ribombee (Bug/Fairy) is weak to Poison, Steel, and Fire. Carkol (Rock/Fire) is weak to Water, Ground, Grass, Ice, and Fighting. Each Pokémon has specific weaknesses that can be exploited in battles.

- **team drawn**: Frogadier (water), Flapple (grass/dragon), Snorunt (ice), Latias (dragon/psychic), Ribombee (bug/fairy), Carkol (rock/fire)
  - **shared weakness** `rock` hits 3/6 → `['Snorunt', 'Ribombee', 'Carkol']`
  - types nobody on the team resists: `['ghost', 'rock']`
  - shared weaknesses the answer named: `['rock']` (named per-Pokémon, never aggregated)
- **type error** (contradiction): "Frogadier (Water/Grass)" — claimed `['water', 'grass']`, actual `['water']`
- **type error** (contradiction): "Flapple (Bug/Fairy)" — claimed `['bug', 'fairy']`, actual `['grass', 'dragon']`
- citations: ['Ribombee Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Ribombee Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Carkol Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Latias Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Snorunt Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: [{'message': 'Frogadier', 'quote': 'Frogadier (Water/Grass)', 'type': 'type_error'}, {'message': 'Flapple', 'quote': 'Flapple (Bug/Fairy)', 'type': 'type_error'}]

#### `team-audit-1` — no-advice · 2.5s

**Q.** Here's my team: Rapidash, Tranquill, Tropius, Pidove, Castform and Naganadel. Identify the type weaknesses in my team.

**A.**
> Your team consists of Rapidash (Fire), Tranquill (Normal/Flying), Tropius (Grass), Pidove (Normal/Flying), Castform (Normal), and Naganadel (Poison/Dragon). Their type weaknesses are: Rapidash (Water, Ground, Rock), Tranquill (Rock, Electric, Ice), Tropius (Fire, Flying, Poison, Rock), Pidove (Rock, Electric, Ice), Castform (Fighting), and Naganadel (Fairy, Ice).

- **team drawn**: Rapidash (fire), Tranquill (normal/flying), Tropius (grass/flying), Pidove (normal/flying), Castform (normal), Naganadel (poison/dragon)
  - **shared weakness** `ice` hits 4/6 → `['Tranquill', 'Tropius', 'Pidove', 'Naganadel']`
  - **shared weakness** `rock` hits 4/6 → `['Rapidash', 'Tranquill', 'Tropius', 'Pidove']`
  - types nobody on the team resists: `['dark', 'dragon', 'flying', 'normal', 'psychic', 'rock']`
  - shared weaknesses the answer named: `['ice', 'rock']` (named per-Pokémon, never aggregated)
- **type error** (incomplete): "Tropius (Grass)" — claimed `['grass']`, actual `['grass', 'flying']`
- **type error** (contradiction): "Castform (Fighting)" — claimed `['fighting']`, actual `['normal']`
- citations: ['Naganadel Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Tranquill Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Tranquill Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: [{'message': 'Tropius', 'quote': 'Tropius (Grass)', 'type': 'type_error'}, {'message': 'Castform', 'quote': 'Castform (Fighting)', 'type': 'type_error'}]

#### `team-audit-2` — no-advice · 3.9s

**Q.** Here's my team: Loudred, Simisear, Grafaiai, Porygon, Iron Treads and Snubbull. Identify the type weaknesses in my team.

**A.**
> Loudred, a Ground-type Pokémon, is weak to Water and Ice moves. Simisear, a Fire-type Pokémon, is weak to Water, Rock, and Ground moves. Grafaiai, a Ghost-type Pokémon, is weak to Dark and Ghost moves. Porygon, a Normal-type Pokémon, is weak to Fighting moves. Iron Treads, a Ground/Steel-type Pokémon, is weak to Ice, Steel, and Water moves. Snubbull, a Fairy-type Pokémon, is weak to Poison and Steel moves.

- **team drawn**: Loudred (normal), Simisear (fire), Grafaiai (poison/normal), Porygon (normal), Iron Treads (ground/steel), Snubbull (fairy)
  - **shared weakness** `fighting` hits 3/6 → `['Loudred', 'Porygon', 'Iron Treads']`
  - **shared weakness** `ground` hits 3/6 → `['Simisear', 'Grafaiai', 'Iron Treads']`
  - types nobody on the team resists: `['ground', 'water']`
  - shared weaknesses the answer named: `['fighting', 'ground']` (named per-Pokémon, never aggregated)
- citations: ['Iron Treads Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Simisear Pokédex: stats, moves, evolution & locations | Pokémon Database', 'Loudred Pokédex: stats, moves, evolution & locations | Pokémon Database']
- server grading flags: `none`

---

### Hand-verified factual errors in Part 2

Every claim below was checked against `eval_harness.typechart.CHART` or PokéAPI directly, not by heuristic.

| Question | Claim in the answer | Ground truth |
|---|---|---|
| `shared-weak` | "Use Rock or Steel typing, these types are strong against Ground" | ground→rock = 2×, ground→steel = 2× (both weak). ground→flying = 0× — never mentioned |
| `role-request` | "Vaporeon has resistances to … Electric" | electric→water = 2× (weak, not resistant) |
| `role-request` | "Hydration restores its HP when it enters battle" | Hydration cures status conditions in rain; restores no HP |
| `who-to-bring` | Recommended Machamp; "Charizard … not as effective … due to its resistance to Fire" | Ferrothorn = Grass/Steel. fire→Ferrothorn = 4×, fighting→Ferrothorn = 2×. Charizard is the correct pick |
| `who-to-bring` | "Fighting-type moves are super effective against Ferrothorn's Grass-type" | fighting→grass = 1×. The 2× comes from Steel, not Grass |
| `hazards` | "Stealth Rock … damages any Pokémon that … uses a move that involves movement" | No such trigger exists; Stealth Rock damages on switch-in only |
| `hazards` | "your team has three Flying types" | The question stated the *opponent* had three Flying types |
| `level-evo` | "Charmeleon evolves from Charmander at level 36" | PokéAPI: charmander→charmeleon at level **16**; charmeleon→charizard at level 36 |
| `branch-evo` | "In Generation 6 and later … evolve Eevee into Umbreon by using a Moon Stone" | PokéAPI: eevee→umbreon is trigger=level-up, happiness=160, time=night, item=None, all gens |
| `split-evo` | "if they are equal, it evolves into Hitmonchan" | PokéAPI: the equal-stat branch is **Hitmontop**, which the answer never mentions |
| `team-audit-2` | "Loudred, a Ground-type Pokémon" | Loudred is **Normal** |
| `team-audit-2` | "Grafaiai, a Ghost-type Pokémon" | Grafaiai is **Poison/Normal** |
| `team-audit-1` | "Tropius (Grass)" | Tropius is **Grass/Flying** |
| `team-audit-0` | "Frogadier (Water/Grass)" | Frogadier is **Water** |
| `team-audit-0` | "Flapple (Bug/Fairy)" | Flapple is **Grass/Dragon** — Bug/Fairy is Ribombee's typing, from later in the same list |

**Grader false positive, for fairness.** `Castform (Fighting)` in `team-audit-1` was flagged as a typing error, but the answer was using `Name (Type)` to mean *weak to* that type in a weakness list, not to assert Castform's typing — which it had stated correctly as Normal earlier in the same answer. The `Name (Type)` pattern is genuinely ambiguous.

---

## Part 3 — Multi-turn journeys

Four continuous sessions. Each journey is one `session_id`, so the coach's history mechanism is in play for every turn after the first. `subject` is what the answer should still be about if the coach were tracking the conversation.

### J1 · New player raises a starter

#### T1 — subject should be `charmander` · abstained, **off-topic** · 0.8s

**Q.** I just caught a Charmander. What should I do with it?

**A.**
> (no answer generated)

- server grading flags: `none`

#### T2 — subject should be `charmander` · 6.3s · similarity to T1: 0.02

**Q.** How does it evolve?

**A.**
> To evolve your Charmander, train it to level 16. Charmander evolves into Charmeleon at this level. Charmeleon can further evolve into Charizard at level 36. Charizard has a dual typing of Fire and Flying, making it a powerful addition to your team. Ensure to level up your Charmander through battles and experience points to achieve these evolutions.

- server grading flags: `none`

#### T3 — subject should be `charmeleon` · 2.5s · similarity to T2: 0.64

**Q.** What level does that happen at?

**A.**
> To evolve your Charmander, train it to level 16, at which point it will evolve into Charmeleon. Charmeleon can then evolve into Charizard at level 36. Charizard has a dual typing of Fire and Flying.

- server grading flags: `none`

#### T4 — subject should be `charizard` · 3.9s · **near-duplicate of T3** (similarity 0.77)

**Q.** Once it's a Charizard, what should I put on my team with it?

**A.**
> Charmander evolves into Charmeleon at level 16. Charmeleon then evolves into Charizard at level 36. Charizard has a dual typing of Fire and Flying.

- server grading flags: `none`

#### T5 — subject should be `charizard` · 5.2s · **near-duplicate of T4** (similarity 0.77)

**Q.** Is it rare?

**A.**
> To evolve your Charmander, train it to level 16, at which point it will evolve into Charmeleon. Charmeleon can then evolve into Charizard at level 36. Charizard has a dual typing of Fire and Flying.

- server grading flags: `none`


### J2 · Mid-battle sequence

#### T1 — subject should be `starmie` · 3.0s

**Q.** I'm battling a gym leader. My lead is Starmie.

**A.**
> Starmie, a Water/Psychic type Pokémon, is a strong choice for battling a gym leader. It has a balanced stat distribution with high Special Attack and Speed, making it versatile in battles. Its ability, Analytic, increases its Special Attack when its HP is low, adding to its strategic depth. Moves like Hydro Pump, Psychic, and Surf can be effective against various gym leaders. However, be mindful of its weaknesses to Bug, Dark, and Ghost-type moves.

- server grading flags: `none`

#### T2 — subject should be `jolteon` · **off-topic** · 4.1s · similarity to T1: 0.23

**Q.** They just sent out a Jolteon. What do I do?

**A.**
> Starmie, a Water/Psychic type Pokémon, is a strong choice for battling a gym leader due to its balanced stat distribution, high Special Attack, and Speed. Its ability, Illuminate, increases its Special Attack in bright sunlight, making it even more formidable. Starmie's core glows in seven colors, earning it the nickname "the gem of the sea." It evolves from Staryu using a Water Stone.

- server grading flags: `none`

#### T3 — subject should be `machamp` · **off-topic** · 2.4s · **identical to T2** (similarity 1.00)

**Q.** Okay, I switched to Snorlax. Now they have a Machamp out.

**A.**
> Starmie, a Water/Psychic type Pokémon, is a strong choice for battling a gym leader due to its balanced stat distribution, high Special Attack, and Speed. Its ability, Illuminate, increases its Special Attack in bright sunlight, making it even more formidable. Starmie's core glows in seven colors, earning it the nickname "the gem of the sea." It evolves from Staryu using a Water Stone.

- server grading flags: `none`

#### T4 — subject should be `snorlax` · 5.4s · similarity to T3: 0.13

**Q.** Should I have stayed in with Snorlax?

**A.**
> Starmie, a Water/Psychic type Pokémon, is effective against Electric types like Jolteon due to its resistance to Electric moves. Its ability, Illuminate, boosts its Special Attack in dark areas, making it even more formidable. To counter Jolteon, use moves like Water Pulse or Psychic to exploit its weaknesses. If you switched to Snorlax, its high HP and powerful moves like Body Slam can be effective against Jolteon.

- server grading flags: `none`


### J3 · Power user auditing a team

#### T1 — subject should be `team` · 2.6s

**Q.** My team is Gyarados, Ferrothorn, Rotom, Landorus, Clefable and Volcarona.

**A.**
> Your team consists of Gyarados, a Water/Flying type known for its volatile temper and destructive potential; Ferrothorn, a Grass/Steel type with strong defensive capabilities; Rotom, an Electric/Ghost type that can possess various appliances; Landorus, a Ground/Flying type embodying abundance; Clefable, a Fairy type with high Special Defense; and Volcarona, a Bug/Fire type with high Special Attack. This team balances offensive and defensive capabilities, with strengths in both physical and special attacks.

- server grading flags: `none`

#### T2 — subject should be `team` · 5.1s · similarity to T1: 0.21

**Q.** Identify the type weaknesses in that team.

**A.**
> Gyarados, a Water/Flying type, is weak to Electric, Rock, and Ice types. Ferrothorn, a Grass/Steel type, is weak to Fire, Ice, and Flying types. Rotom, an Electric/Ghost type, is weak to Ghost, Dark, and Ground types. Landorus, a Ground/Flying type, is weak to Electric, Ice, and Rock types. Clefable, a Fairy type, is weak to Poison and Steel types. Volcarona, a Bug/Fire type, is weak to Rock, Water, and Ground types.

- server grading flags: `none`

#### T3 — subject should be `team` · 6.4s · **near-duplicate of T2** (similarity 0.77)

**Q.** Which one is the biggest liability?

**A.**
> Gyarados, a Water/Flying type, is weak to Electric, Rock, and Ice moves. Ferrothorn, a Grass/Steel type, is weak to Fire, Ice, and Flying moves. Rotom, an Electric/Ghost type, is weak to Ground and Ghost moves. Landorus, a Ground/Rock type, is weak to Water and Grass moves. Clefable, a Fairy type, is weak to Poison and Steel moves. Volcarona, a Bug/Fire type, is weak to Rock, Water, and Flying moves.

- server grading flags: `none`

#### T4 — subject should be `team` · 3.8s · similarity to T3: 0.10

**Q.** What should I swap it for?

**A.**
> Gyarados is weak to Electric, Rock, and Ice types. Ferrothorn is weak to Fire, Ice, and Flying types. Rotom is weak to Ghost and Dark types. Given these weaknesses, Ferrothorn's vulnerability to Fire and Flying types could be the biggest liability, as these types are more commonly encountered in various Pokémon battles.

- server grading flags: `none`


### J4 · Rarity and evolution mixed

#### T1 — subject should be `feebas` · 2.5s

**Q.** Is Feebas rare?

**A.**
> Feebas is indeed rare. In Ruby, Sapphire, and Emerald, it can only be found by fishing in one of six random squares on Route 119. In Diamond, Pearl, and Platinum, it is available in one of four random squares in Mt. Coronet. Its rarity is further emphasized by its shabby appearance, which makes it largely ignored by researchers and trainers alike.

- server grading flags: `none`

#### T2 — subject should be `feebas` · 2.9s · similarity to T1: 0.34

**Q.** How do I evolve it?

**A.**
> Feebas is rare, found in specific locations in various games. In Ruby, Sapphire, and Emerald, it's available in one of six random squares on Route 119. In Diamond, Pearl, and Platinum, it's in one of four random squares in Mt. Coronet. To evolve Feebas into Milotic, in Ruby, Sapphire, Emerald, Diamond, Pearl, and Platinum, maximize its Beauty stat with Poffins. From Black and White onwards, it evolves when traded holding a Prism Scale, or if migrated with maximum Beauty.

- server grading flags: `none`

#### T3 — subject should be `feebas` · 3.8s · similarity to T2: 0.44

**Q.** Can I just use a Water Stone instead?

**A.**
> Feebas is rare and can be found by fishing in specific locations. In Ruby, Sapphire, and Emerald, it is available in one of six random squares on Route 119. In Diamond, Pearl, and Platinum, it is found in one of four random squares on Route 119. To evolve Feebas into Milotic, you need to increase its Beauty condition to the maximum level. This can be achieved by using the item Soothe Bell and leveling up Feebas in battle.

- server grading flags: `none`

#### T4 — subject should be `milotic` · abstained · 7.6s · similarity to T3: 0.05

**Q.** What about Milotic, is that rare too?

**A.**
> (RGA model did not trigger. Top result: It leaks water that looks like tears when adjusting its moisture level. ... It discharges moisture from its eyes, making it look like it’s crying—apparently an effective way of getting ...; It’s capable of spending a limited amount of time on land. ... It used to have a shell on its back long ago. ... Seafolk Village Let's Go Pikachu Let's Go Eevee Not available in this game; It has the power to becalm such emotions as anger and hostility to quell bitter feuding. ... It’s said that a glimpse of a Milotic and its beauty will calm any hostile emotions you’re ...)

- server grading flags: `none`


### Cross-turn contradictions inside a single session

**J2 — three descriptions of one ability, same session, same Pokémon:**

| Turn | Claim | Reality |
|---|---|---|
| T1 | "Its ability, **Analytic**, increases its Special Attack **when its HP is low**" | Analytic boosts power when the user moves last, not at low HP |
| T2 | "Its ability, **Illuminate**, increases its Special Attack **in bright sunlight**" | Illuminate does not affect Special Attack |
| T4 | "Its ability, **Illuminate**, boosts its Special Attack **in dark areas**" | Contradicts T2 and is also wrong |

**J2 T4 — the one decision-shaped question in the session, answered backwards:**

> "Starmie … is effective against Electric types like Jolteon due to its **resistance to Electric moves**."

Starmie is Water/Psychic. `electric → water/psychic = 2×`. Staying in loses Starmie.

**J3 — the same team, audited over three consecutive turns:**

| Pokémon | T1–T2 | T3 | Actual |
|---|---|---|---|
| Landorus | Ground/Flying | **Ground/Rock** | Ground/Flying |
| Rotom | weak to Ghost, Dark, Ground | weak to Ground, Ghost | — |
| Volcarona | weak to Rock, Water, Ground | weak to Rock, Water, Flying | — |

T2 also states "Landorus … is weak to Electric". `electric → ground/flying = 0×` — Landorus is **immune**.

---

## Part 4 — Pure-function fuzzing

Adversarial input to `_detect_comparison`, `_extract_pokemon_mentions` and `_build_context_prompt`, with no network. Re-run against the current working tree after the mid-session edit to `coach_api.py`.

Script: `t1_pure.py`

_(see Part 9 for the re-run summary)_

---

## Part 5 — Protocol and abuse

Sixteen malformed payloads against `POST /api/coach`, plus session-isolation, XSS, prompt-injection and false-premise probes. Note: the session-introspection lines in this log read `0` because the script ran in a separate process from the Flask server and so held its own empty in-memory store — those checks were redone in-process in Part 6.

Script: `t3_abuse.py`

```
null bytes remaining: 0
### 1. Malformed / hostile payloads to /api/coach
  no body                -> 400     0.0s  '<!doctype html>\n<html lang=en>\n<title>400 Bad Request</title>\n<h1>Bad Request</h1>\n<p>The browser (or proxy) s'
  not json               -> 400     0.0s  '<!doctype html>\n<html lang=en>\n<title>400 Bad Request</title>\n<h1>Bad Request</h1>\n<p>The browser (or proxy) s'
  json array             -> 500     0.0s  '<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>\n<h1>Internal Server Error</h1>\n<p>The '  <-- 500 UNHANDLED
  json string            -> 500     0.0s  '<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>\n<h1>Internal Server Error</h1>\n<p>The '  <-- 500 UNHANDLED
  json null              -> 400     0.0s  '{"error":"session_id is required"}\n'
  missing session_id     -> 400     0.0s  '{"error":"session_id is required"}\n'
  missing message        -> 400     0.0s  '{"error":"message is required"}\n'
  empty strings          -> 400     0.0s  '{"error":"session_id is required"}\n'
  session_id is int      -> 500     0.0s  '<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>\n<h1>Internal Server Error</h1>\n<p>The '  <-- 500 UNHANDLED
  message is int         -> 500     0.0s  '<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>\n<h1>Internal Server Error</h1>\n<p>The '  <-- 500 UNHANDLED
  message is list        -> 500     0.0s  '<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>\n<h1>Internal Server Error</h1>\n<p>The '  <-- 500 UNHANDLED
  message is dict        -> 500     0.0s  '<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>\n<h1>Internal Server Error</h1>\n<p>The '  <-- 500 UNHANDLED
  session_id 100KB       -> 200     0.4s  '{"answer":"(no answer generated)","citations":[],"comparison":null,"grading_flags":[],"session_id":"ssssssssss'
  message 200KB          -> 200     0.3s  '{"answer":"(Error: Coveo search error: 400)","citations":[],"comparison":null,"grading_flags":[],"session_id":'
  null byte in msg       -> 200     5.8s  '{"answer":"Charizard is a Fire/Flying type Pok\\u00e9mon, introduced in Generation 1. It evolves from Charmeleo'
  rtl override unicode   -> 200     2.9s  '{"answer":"Drowzee is a Psychic-type Pok\\u00e9mon introduced in Generation 1. It evolves into Hypno at level 2'

### 2. Session isolation
  cross-session leak: no leak
  B answer: '(no answer generated)'
  session A turns stored: 0

### 3. XSS payload round-trip
  answer: '(no answer generated)'
  comparison fired: False

### 4. Prompt injection through the message
  obeyed?: False
  answer: '(Error: Internal server error.)'

### 5. False-premise contamination via history
  answer: '(no answer generated)'
  server flags: []

### 6. Memory window: does the wild Pokemon survive eviction?
  stored turns: 0 (MAX_TURNS=20)
Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-anuragkaushik137-Documents-AC-Feedback-interview-for-IBM/001e5ead-8875-44df-bbdf-256f56b42421/scratchpad/rip/t3_abuse.py", line 106, in <module>
    print(f"  oldest turn now: {h[0]['content'][:70]!r}")
                                ~^^^
IndexError: list index out of range

[exited with code 1]
```

---

## Part 6 — Conversation state (in-process)

Re-run of the state checks through a Flask test client, so the `pokedex.conversation` store is the same object the routes mutate.

Script: `t4_state.py`

```
### A. Challenge mode: does the probe get stored twice?
  prompt   : 'My team is Iron Thorns, Mienfoo, Flamigo, Quilava, Snubbull and Brionne. Which of these has a type advantage against Tor'
  scenario : {"axis": "baseline", "team": ["Iron Thorns", "Mienfoo", "Flamigo", "Quilava", "Snubbull", "Brionne"], "wild": "Torracat"}
  BEFORE client sends: 1 turns, roles=['user']
  --> query that /api/coach will build from that history:
      Trainer: My team is Iron Thorns, Mienfoo, Flamigo, Quilava, Snubbull and Brionne. Which of these has a type advantage against Torracat?
      Trainer: My team is Iron Thorns, Mienfoo, Flamigo, Quilava, Snubbull and Brionne. Which of these has a type advantage against Torracat?
  AFTER  : 3 turns, roles=['user', 'user', 'assistant']
  duplicate user turns: True  (2 user turns)

### B. Turn accounting on a normal 3-question conversation
  turns: 6 roles=['user', 'assistant', 'user', 'assistant', 'user', 'assistant']
  pokemon_context per turn: [['tell', 'lapras'], ['tell', 'lapras'], [], [], ['kingdra'], ['kingdra']]

### C. Does the 20-turn cap evict the original question?
  turns: 20 (MAX_TURNS=20)
  oldest surviving turn: 'Filler 0: name a Normal type.'
  'Tyranitar' still in history: True

### D. Session eviction under load (MAX_SESSIONS=1000)
  sessions held: 1000
  session 0 survived: False
  session 1004 survived: True

### E. get_or_create is defined but never called anywhere
  ./tests/unit/test_conversation.py:6:    from pokedex.conversation import get_or_create, clear
  ./tests/unit/test_conversation.py:8:    turns = get_or_create("s1")
  ./pokedex/conversation.py:25:def get_or_create(session_id: str) -> list[dict]:

[exited with code 0]
  [132 third-party .venv matches elided]
```

---

## Part 7 — Retrieval isolation A/B

The controlled experiment: the identical battle question asked cold vs. after one lookup turn, plus the raw Coveo search results for the bare question vs. the context blob the coach actually sends.

Script: `t5_isolate.py`

```
==============================================================================
ARM 1 — cold session: the advantage question is the FIRST message
==============================================================================
[1.9s] (no answer generated)

==============================================================================
ARM 2 — warm session: same question AFTER a lookup turn (what the UI does)
==============================================================================
  (turn 1 lookup: Toucannon is a Normal/Flying type Pokémon introduced in Generation 7. It evolves from Trumbeak at level 28. Toucannon st...)
[3.4s] Toucannon is a Normal/Flying type Pokémon introduced in Generation 7, evolving from Trumbeak at level 28. It stands 1.1 meters tall and weighs 26.0 kg. Toucannon has a base Friendship of 70 and can have abilities like Keen Eye, Skill Link, and Sheer Force (hidden). It has a Catch rate of 45 and a Medium Fast growth rate. Toucannon's base stats include HP 80, Attack 120, Defense 75, Sp. Atk 75, Sp. Def 75, and Speed 60. It learns moves like Echoed Voice, Peck, Rock Blast, and Drill Peck. Toucannon can be found in locations like Route 11, Poni Grove, and Poni Plains.

==============================================================================
RETRIEVAL: what Coveo actually returns for each query string
==============================================================================

  bare question  (149 chars)
    totalCount=30
      - Pokémon Pokédex: list of Pokémon with stats | Pokémon Database
      - List of Pokémon (sprites gallery) | Pokémon Database
      - Pokémon Shiny-dex (list of shiny sprites) | Pokémon Database
      - Gothita Pokédex: stats, moves, evolution & locations | Pokémon Database
      - Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database
      - Gothorita Pokédex: stats, moves, evolution & locations | Pokémon Database
    team members retrieved: ['Gothita']
    wild retrieved: True

  context blob (what coach sends)  (399 chars)
    totalCount=500
      - Toucannon Pokédex: stats, moves, evolution & locations | Pokémon Database
      - Trumbeak Pokédex: stats, moves, evolution & locations | Pokémon Database
      - Pokémon Shiny-dex (list of shiny sprites) | Pokémon Database
      - Solosis Pokédex: stats, moves, evolution & locations | Pokémon Database
      - List of Pokémon (sprites gallery) | Pokémon Database
      - Venipede Pokédex: stats, moves, evolution & locations | Pokémon Database
    team members retrieved: ['Venipede', 'Solosis']
    wild retrieved: True

[exited with code 0]
```

---

## Part 8 — Browser (headless Chromium)

Nine probes of the rendered `/coach` page.

Script: `t6_frontend.py`

```
### 1. Comparison OVERFIRE — a benign question with the word 'or'
  .cmp-card rendered      : 2   (expected 0)
  'Pokémon not found' msgs: 2
  card names: []
  verdict bar: ['⚑ Equal BST. (no answer generated)']

### 2. Legitimate comparison — is the answer rendered twice?
  oak bubbles: 1
    bubble : 'Gyarados is a Water/Flying type Pokémon, while Vaporeon is a Water type. Gyarados is known for its destructive power and volatile temper, often linked'
    verdict: '⚑ Gyarados has higher BST (540 vs 525). Gyarados is a Water/Flying type Pokémon, while Vaporeon is a Water type. Gyarados is known for its destructive power and volatile temper, often linked with tale'
  ANSWER DUPLICATED in verdict bar: True
  cmp cards: 2

### 3. Grading flag rendering — Meganium hallucination
  answer  : 'Meganium is a Grass/Fairy type Pokémon introduced in Generation 2. It evolves from Bayleef at level 32. Known as the Herb Pokémon, it has a height of 1.8 meters and weighs 100.5 kg'
  flags UI: ['⚠ Type error: Meganium']   <-- does this tell the user WHAT is wrong?
  snippet : 'Meganium is a Grass/Fairy type Pokémon introduced in Generation 2.'
  'Similar Pokémon' recs: ['Bellossom', 'Hoppip', 'Vileplume']

### 4. Challenge chip
  user bubbles : 1
  oak bubbles  : 1
  error bubbles: 0
  thinking still spinning: 0
  challenge prompt: 'My team is Vileplume, Cascoon, Sandslash, Wurmple, Sceptile and Maschiff. Which of these has a type advantage against Houndstone?'
  oak reply       : 'Houndstone is a Ghost-type Pokémon. Ghost-type moves are ineffective against Ghost-type Pokémon, but they are weak against Dark and Ghost-type moves. Among your team, Maschiff, being a Dark-type Pokémon, has a type advantage against Houndstone.'
  send button disabled (stuck busy?): False

### 5. Double-send race — click send twice fast
  second click blocked (button disabled) — busy guard holds
  user bubbles: 1 (expect 1)
  oak bubbles : 1 (expect 1)

### 6. URL-param comparison entry point (?compare=X&with=Y)
  cmp cards: 2
  names    : ['Charizard', 'Blastoise']
  verdict  : '⚑ Charizard has higher BST (534 vs 530). Charizard and Blastoise are both final evolutions of the original starter Pokémon from Generation 1. Charizard is a Fire/Flying type, while Blastoise is a Wate'

### 7. Injection through the answer text (is esc() enough?)
  raw <img> element injected into DOM: 0
  bubble html: '<div class="bubble-oak-header"><div class="oak-dot"></div>Professor Oak</div><div class="bubble-oak-text">(no answer generated)</div>'

### Console errors / warnings collected
  warning: Using `value="false"` for a boolean attribute is not compliant with HTML standards (see https://html.spec.whatwg.org/#boolean-attributes). This behavior will not be supported in Atomic v4. To
  error: Failed to load resource: the server responded with a status of 404 ()

[exited with code 0]
```

---

### Part 4 addendum — comparison detector, current working tree

Re-run after the mid-session edit. Unchanged: 5 of 10 benign questions still trigger a comparison panel.

```

### A. _detect_comparison — should FIRE
  ok    fires: 'Compare Charizard and Dragonite'
  ok    fires: 'compare Gyarados vs Vaporeon'
  ok    fires: 'Charizard vs Dragonite'
  ok    fires: 'Umbreon versus Espeon'
  ok    fires: 'Which is better: Umbreon or Espeon?'
  ok    fires: 'Between Snorlax and Blissey, who walls better?'
  ok    fires: 'Compare Mr. Mime and Mime Jr.'
  ok    fires: 'Nidoran♀ vs Nidoran♂'
  ok    fires: 'Compare Ho-Oh and Lugia'
  FAIL  fires: 'Porygon-Z or Porygon2 for my team?'
        got None (name shape unsupported)

### B. _detect_comparison — should NOT fire (false positives)
  ok    quiet: 'Should I evolve my Eevee or wait until level 30?'
  FAIL  quiet: 'Is Charizard good or bad in this matchup?'
        spuriously matched ('is charizard good', 'bad in this matchup')
  ok    quiet: 'Tell me about Snorlax'
  ok    quiet: 'What is the best move for my team of six?'
  ok    quiet: 'I lost the battle. Was that bad luck or bad type coverage?'
  FAIL  quiet: 'Can you explain STAB versus base power for me?'
        spuriously matched ('can you explain stab', 'base power for me')
  FAIL  quiet: 'Rate my team out of ten or give me a grade'
        spuriously matched ('rate my team out of ten', 'give me a grade')
  FAIL  quiet: 'My Pikachu fainted. Should I heal it or switch out?'
        spuriously matched ('fainted. should i heal it', 'switch out')
  FAIL  quiet: 'Do I lead with the tank or the sweeper?'
        spuriously matched ('do i lead with the tank', 'the sweeper')
  ok    quiet: 'Which one wins, and why?'

### C. _extract_pokemon_mentions
  ok    mentions: 'My team is Charizard, Snorlax and Gengar.'
  FAIL  mentions: 'Tell me about Mewtwo'
        want {'mewtwo'} got {'tell', 'mewtwo'}
  FAIL  mentions: 'Which Pokemon should I use?'
        want set() got {'pokemon'}
  FAIL  mentions: 'I Am Shouting Every Word Here'
        want set() got {'shouting', 'here', 'word', 'every'}

### D. _build_context_prompt
  ok    history is capped
  ok    new question is last
  ok    no duplicate trainer turns

### E. what actually gets sent to Coveo as the SEARCH QUERY
  query length: 387 chars, 64 words
  --- verbatim query sent to Coveo /rest/search/v2 ---
  Trainer: Tell me about Meganium
  Oak: Meganium is a Grass-type Pokemon introduced in Generation II. It evolves from Bayleef at level 32 and is the final form of Chikorita.
  Trainer: My team is Charizard, Dragonite, Pikachu, Slakoth, Starmie, Geodude. Which has a type advantage against Meganium?
  Oak: Charizard has an advantage due to its Fire typing.
  Trainer: Which of them is a bad idea?

=== 9 failures ===
```

---

## Part 9 — Aggregates

### Battle battery verdicts

| Probe | correct | partial | wrong | abstained |
|---|---|---|---|---|
| `lookup` | 7 | 0 | 0 | 0 |
| `advantage` | 1 | 0 | 5 | 1 |
| `avoid` | 1 | 0 | 5 | 1 |
| `pronoun` | 0 | 1 | 6 | 0 |
| `unnamed_team` | 1 | 0 | 6 | 0 |
| **total** | **10** | **1** | **22** | **2** |

### Does the answer engage with the team at all?

| Probe | turns naming ≥1 teammate |
|---|---|
| `advantage` | 0/7 |
| `avoid` | 0/7 |
| `pronoun` | 7/7 |
| `unnamed_team` | 1/7 |

The `advantage` and `avoid` turns are the two that *ask about the team*. Neither named a single teammate in any of the seven scenarios. The `pronoun` turn, which asks about the wild Pokémon, named teammates in all seven — the answer to the team question arrives two turns after it was asked.

### Harmful recommendations (battle battery)

| Scenario | Probe | Recommended | Why it cannot win |
|---|---|---|---|
| S3 | `pronoun` | Grookey | takes 2x and hits for only 0.25x |
| S3 | `pronoun` | Kabutops | takes 4x and hits for only 1x |
| S3 | `pronoun` | Mienshao | takes 1x and hits for only 0.5x |
| S3 | `unnamed_team` | Grookey | takes 2x and hits for only 0.25x |
| S3 | `unnamed_team` | Kabutops | takes 4x and hits for only 1x |
| S3 | `unnamed_team` | Mienshao | takes 1x and hits for only 0.5x |
| S4 | `pronoun` | Iron Treads | has a ground STAB that deals 0x |
| S5 | `pronoun` | Castform | takes 1x and hits for only 0.5x |
| S5 | `pronoun` | Tropius | takes 1x and hits for only 0.5x |
| S7 | `pronoun` | Floatzel | takes 2x and hits for only 0.5x |

### Player-intent battery by theme

| Theme | n | declined | no advice | advised |
|---|---|---|---|---|
| A · Team building | 5 | 3 | 0 | 2 |
| B · In-battle decisions | 5 | 3 | 0 | 2 |
| C · Evolution | 6 | 1 | 5 | 0 |
| D · The rest of the game | 6 | 4 | 2 | 0 |
| E · Rare encounter | 5 | 2 | 1 | 2 |
| F · Power user | 3 | 0 | 3 | 0 |
| **total** | **30** | **13** | **11** | **6** |

Abstention rate: **13/30 = 43%**

### Journey answer repetition

| Journey | Turn pair | Similarity | |
|---|---|---|---|
| J1 | T1→T2 | 0.02 |  |
| J1 | T2→T3 | 0.64 |  |
| J1 | T3→T4 | 0.77 | **near-duplicate** |
| J1 | T4→T5 | 0.77 | **near-duplicate** |
| J2 | T1→T2 | 0.23 |  |
| J2 | T2→T3 | 1.00 | **identical** |
| J2 | T3→T4 | 0.13 |  |
| J3 | T1→T2 | 0.21 |  |
| J3 | T2→T3 | 0.77 | **near-duplicate** |
| J3 | T3→T4 | 0.10 |  |
| J4 | T1→T2 | 0.34 |  |
| J4 | T2→T3 | 0.44 |  |
| J4 | T3→T4 | 0.05 |  |

**4/13** consecutive turn-pairs returned a near-duplicate answer despite a different question.

### Grader coverage — the same false claim, seven phrasings

`_grade_answer()` on the identical fabrication about Loudred (actual typing: Normal). Both names in the failing team audit **are** in the type cache, so this is a phrasing gap, not the cache-coverage gap.

| Phrasing | Flagged? |
|---|---|
| `Loudred is a Ground-type Pokemon.` | yes |
| `Loudred, which is a Ground-type Pokemon, is weak to Water.` | yes |
| `Loudred (Ground) is weak to Water.` | yes |
| `Loudred's Ground-type moves are strong.` | yes |
| `Loudred, a Ground-type Pokemon, is weak to Water.` | **no** |
| `Loudred, a Ground type, is weak to Water.` | **no** |
| `Your Loudred is Ground-type so it fears Water.` | **no** |

The appositive — `Name, a X-type Pokémon` — is the phrasing the model reaches for most often in list answers, and it is the one form `TYPE_CLAIM_PATTERNS` does not cover.

### Type-cache coverage

- `eval_data/type_cache.json`: **315** entries
- `eval_data/corpus.json`: **924** names
- Corpus names with no cache entry: **623** (67%)

The chart is built with `offline=True`, so an uncached name raises inside `check_type_claims`, hits a bare `except: continue`, and the claim passes unchecked. Notable misses:

| Name | In cache |
|---|---|
| Charizard | **no** |
| Pikachu | **no** |
| Starmie | **no** |
| Slakoth | **no** |
| Meganium | yes |
| Geodude | yes |
| Dragonite | yes |

### Latency

- n = 82 turns
- min **0.6s** · median **3.0s** · p90 **6.1s** · max **9.04s**

---

## Appendix A — Scripts and reproduction

All scripts live in the session scratchpad and are self-contained; each takes the running app at `127.0.0.1:5003` as its target.

| Script | What it does |
|---|---|
| `t1_pure.py` | Fuzzes `_detect_comparison`, `_extract_pokemon_mentions`, `_build_context_prompt`. No network. |
| `t2_battle.py` | Draws 7 scenarios by axis, runs 5 probes each, grades with `eval_harness.grading.grade_turn`. → `battle_results.json` |
| `t3_abuse.py` | 16 malformed payloads plus isolation / XSS / injection probes. |
| `t4_state.py` | Conversation-store checks through a Flask test client. |
| `t5_isolate.py` | Cold vs. warm A/B and raw Coveo retrieval comparison. |
| `t6_frontend.py` | 9 headless-Chromium probes of `/coach`. |
| `t7_analyse.py` | Aggregates `battle_results.json`. |
| `g1_gamer.py` | 30 player-intent questions across 6 themes, with PokéAPI evolution ground truth and computed team-weakness truth. → `gamer_results.json` |
| `g2_journey.py` | 4 continuous sessions, 17 turns. → `journey_results.json` |
| `g3_analyse.py` | Cross-suite aggregation and hand-verified error table. |
| `mkreport.py` | Generates this file from the three result JSONs and the run logs. |

To reproduce:

```bash
make run &                       # app on 127.0.0.1:5003
python t2_battle.py              # wild-encounter battery
python g1_gamer.py               # player-intent battery
python g2_journey.py             # multi-turn journeys
python mkreport.py               # regenerate this document
```

### Gap worth closing

`eval_harness` has scenarios, axes, a grader, a SQLite store and exporters, but **no backend client for `/api/coach`** — `backends.py` only speaks to `/api/rga-coveo` and `/api/rga`. None of the multi-turn results in this document are currently reproducible through `make eval`. Adding a `CoachClient` alongside `AppClient` would put every turn here into the database the harness already has, which is the point of having built it.
