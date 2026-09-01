# Learning path: Pi cluster in a 2006 Odyssey

Ordered so that each stage removes a way to destroy hardware, injure yourself,
or strand the van. Check things off as you go.

## Critical path — do these first

- [ ] **The Car Hacker's Handbook**, Craig Smith (No Starch Press). OBD-II,
      CAN, bus tooling, reverse engineering. The single best book for the data
      half of this project.
- [ ] **Wikipedia: OBD-II PIDs.** The practical PID reference. Every decoder in
      `tools/probe_obd.py` came from here.
- [ ] **CSS Electronics' free CAN / OBD-II intros** (csselectronics.com). Best
      free explanation of CAN framing, OBD-II request/response and DBC files.
- [ ] **ScannerDanner** (YouTube + *Engine Performance Diagnostics*). How to
      reason about a car circuit and probe it without breaking it.
- [ ] **Automotive Electrical Handbook**, Jim Horner (HP Books). Dated but the
      fundamentals — wire gauge, fusing, relays, grounds — are timeless.

## Automotive electrical

- [ ] *Automotive Wiring and Electrical Systems* Vol 1 & 2, Tony Candela (CarTech)
- [ ] *How to Diagnose and Repair Automotive Electrical Systems*, Tracy Martin
- [ ] *Bosch Automotive Handbook* — dense reference, not a read-through
- [ ] YouTube: **South Main Auto Repair** (real-world electrical diagnosis),
      **Pine Hollow Auto Diagnostics** (advanced, CAN diagnosis),
      **Diagnose Dan** (scope work on live circuits)
- [ ] Concepts to be able to explain before wiring anything: load dump,
      ISO 7637-2 transients, voltage drop vs. wire gauge and length, why a
      circuit is fused for the *wire* and not the load, star grounding and
      ground loops, relay coil suppression diodes

## Vehicle data buses

- [ ] *A Comprehensible Guide to Controller Area Network*, Wilfried Voss
- [ ] Standards worth skimming: SAE J1962 (connector), SAE J1979 (diagnostic
      modes), ISO 9141-2 (K-line), ISO 15765-4 (CAN diagnostics)
- [ ] Tools to learn: `can-utils` (`candump`, `cansniffer`, `cangen`),
      `python-can`, **SavvyCAN** (open-source CAN reverse engineering),
      **ELM327-emulator**, **py-obdii**
- [ ] Communities: r/carhacking, obdb.community (community signal database)

## Electronics fundamentals

- [ ] **All About Circuits** free textbook series, Tony Kuphaldt
      (allaboutcircuits.com) — start here, it's free and thorough
- [ ] *Make: Electronics*, Charles Platt — hands-on, best beginner book
- [ ] *Encyclopedia of Electronic Components* Vol 1–3, Charles Platt — the
      lookup reference you'll actually reach for
- [ ] *Practical Electronics for Inventors*, Scherz & Monk — the one-volume
      workhorse
- [ ] *The Art of Electronics*, Horowitz & Hill — reference, not a first read
- [ ] SparkFun and Adafruit learn portals — specifically their optocoupler,
      level-shifting, and power-supply guides
- [ ] YouTube: **Afrotechmods** (best short fundamentals), **EEVblog**
      (multimeter/scope technique), **Great Scott!** (buck converters,
      battery circuits), **Ben Eater** (protocols and digital logic),
      **ElectroBoom** (safety and measurement, by counterexample),
      **Big Clive** (teardowns, reality checks on cheap modules)
- [ ] MIT OCW 6.002 *Circuits and Electronics*, if you want the theory
- [ ] Specific circuits for this build: PC817 optocoupler as a 12V logic
      sense, resistor divider sizing, RC debounce, buck converter selection
      and input protection, TVS/flyback diodes

## Raspberry Pi in a vehicle

- [ ] Official Raspberry Pi documentation — GPIO, config.txt, KMS
- [ ] `SDL_VIDEODRIVER=kmsdrm` for pygame with no X server
- [ ] systemd unit files: `Restart=always`, `After=`, boot-to-app
- [ ] Read-only root via overlayfs (`raspi-config`) — the real fix for SD
      card corruption
- [ ] Ignition-sense shutdown hardware: Mausberry car shutdown controllers,
      Witty Pi (UUGear), PiJuice, LiFePO4wered/Pi
- [ ] *Raspberry Pi Cookbook*, Simon Monk
- [ ] YouTube: **Andreas Spiess** (rigorous, good on power and CAN modules),
      **DroneBot Workshop** (clear GPIO/interface tutorials)

## Mechanical, enclosure and mounting

- [ ] Fusion 360: **Lars Christensen**, **Product Design Online** (Kevin Kennedy)
- [ ] **CNC Kitchen** (Stefan Hermann) — material strength and, critically,
      heat/creep testing. PLA will sag on a sunlit dashboard; watch his
      temperature tests before choosing filament. Use PETG, ASA or ABS.
- [ ] **Thomas Sanladerer** — general 3D printing competence
- [ ] **SuperfastMatt** — automotive fabrication and electronics integration,
      closest in spirit to what you're building
- [ ] **This Old Tony** — fabrication and machining fundamentals
- [ ] **Cechaflo** — automotive upholstery, if you want to wrap the pod in
      matching vinyl
- [ ] Topics: 3M VHB surface prep, threaded inserts in prints, vibration
      isolation and strain relief, passive venting, automotive-grade adhesives

## Honda-specific

- [ ] **techinfo.honda.com** — factory service manual and wiring diagrams by
      subscription. Buy a short subscription; the wiring diagrams tell you
      exactly which wire and which color to tap. This is the difference
      between engineering and guessing.
- [ ] **odyclub.com** — model-specific forum, wiring and trim removal threads
- [ ] Helm Inc. — printed factory manuals
- [ ] ALLDATA or Mitchell1 DIY as alternatives

## Hands-on before you touch the van

- [ ] Multimeter technique: continuity, voltage drop under load, current via
      shunt. Voltage drop testing is the skill that separates real diagnosis
      from guessing.
- [ ] Cheap 2-channel scope (Hantek or similar) — look at K-line and CAN
      signals so you know what healthy looks like
- [ ] Crimping: proper open-barrel crimpers, adhesive-lined heat shrink,
      Deutsch DT or Molex connectors. Practice 20 crimps and pull-test them.
      Never use vampire/Scotchlok taps — they are the leading cause of
      electrical gremlins.
- [ ] Bench the whole system on a 12V supply with a current limit before it
      goes near the vehicle
- [ ] Build the opto-isolated 12V sense circuit on a breadboard and prove it
      on a bench supply, not on the van

## Safety non-negotiables

- [ ] **Never probe, cut or unplug yellow connectors.** Yellow means SRS
      (airbags). A deployment at close range is a serious injury.
- [ ] Disconnect the battery negative before working under the dash, and wait
      before touching SRS-adjacent areas.
- [ ] Every 12V tap gets its own fuse, sized for the wire.
- [ ] Do not splice into CAN or K-line destructively — sniff passively at the
      OBD-II connector.
- [ ] Leave the factory cluster installed and working. It carries legally
      required indicators and it's your calibration ground truth.
- [ ] Check your jurisdiction's rules on screens in the driver's forward field
      of view before committing to a center-dash-top mount.
- [ ] Implement night dimming before driving after dark. A bright screen
      reflecting off the windshield is a genuine hazard.
