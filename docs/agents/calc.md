# Rechnung

Kein Modell. `agent/agent.py` `build_facts` führt die Ergebnisse zusammen, `agent/calc.py` `compute` rechnet.

## Regeln

3 (no_bid), 4, 6, 7, 8, 15, 16, 18, 22–27.

## build_facts

Pro Position aus Anforderung, Konditionen und ERP: Menge, Material, Staffeln (Zahl im Format der Kondition geparst,
`number`), Preiseinheit, Währung und Kurs, Zuschlagsmasse in kg (`grams_to_kg`) × Metallindex, Rüstgebühr aus Mail
und ERP, Rabatt-Regel, Bestand, Lieferzeiten, Lieferzusage, Kartongröße und -preis, Pool- und Bonus-Mitgliedschaft,
Allokationsmasse. Dazu Referenz, Rabatt, Pool-Gebühr, Bonus-Staffeln.

## compute

1. Fehlt bei einer Position das Material: `no_bid`, keine Positionen, Summe 0; bedingte Freigabe → 0 %.
2. Basispreis = Staffelpreis (höchste erreichte Staffel, `scale_price`) / Preiseinheit × Kurs, auf Cent.
3. Bestellwert vor Rabatt = Σ Menge × Basis. Unter `min_order_value` → 0 %.
4. Bedarf je Material über alle Positionen summieren (gemeinsamer Bestand, Lieferzusage).
5. Rüstpool nach Menge × Allokationsmasse verteilen, Projektbonus über marginale Staffeln (`bonus_credit`) und nach
   Warenwert verteilen. Beides mit `allocate`: Cent abrunden, Rest an die größten Reste, Gleichstand nach Position.
6. Endpreis = Basis (rabattiert je Regel) + Zuschlag (rabattiert nur bei `base_and_surcharge`)
   + (Rüstung + Pool-Anteil + Verpackung − Bonus) / Menge, einmal HALF_UP.
7. Lieferzeit: Zusage, wenn Material passt und Bedarf ≤ Obergrenze; sonst Lager, wenn Bestand ≥ Bedarf; sonst
   Produktion.
8. Summe = Σ Menge × Endpreis, auf Cent. Dazu ein Rechenprotokoll (`trace`) für die Logs.

Gemeldet werden Basis, Zuschlag je Stück (Masse + Rüstung, vor Rabatt), Verpackung je Stück und Bonus je Position.

## Offen

- Schritt 1 unterscheidet nicht zwischen „kein Material“ und „ERP-Agent gescheitert“ (siehe [erp.md](erp.md#offen)).
  Im zweiten Fall sollte die Position ausgelassen statt `no_bid` werden; No-Bid kostet bei einem Bid-Szenario fast
  alle Positionspunkte.
