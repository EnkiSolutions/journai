-- Refuser les données historiques incohérentes avant d'installer les garde-fous.
CREATE TABLE controle_integrite_numerique (
  valide INTEGER CONSTRAINT donnees_numeriques_invalides CHECK (valide = 1)
);
INSERT INTO controle_integrite_numerique
SELECT 0 FROM estimation_action
WHERE charge_min_h > charge_max_h OR cout_min > cout_max
UNION ALL
SELECT 0 FROM mesure_indicateur WHERE typeof(valeur) NOT IN ('integer', 'real')
LIMIT 1;
DROP TABLE controle_integrite_numerique;

CREATE TRIGGER estimation_bornes_insert BEFORE INSERT ON estimation_action
WHEN NEW.charge_min_h > NEW.charge_max_h OR NEW.cout_min > NEW.cout_max
BEGIN
  SELECT RAISE(ABORT, 'bornes estimation invalides');
END;

CREATE TRIGGER estimation_bornes_update BEFORE UPDATE ON estimation_action
WHEN NEW.charge_min_h > NEW.charge_max_h OR NEW.cout_min > NEW.cout_max
BEGIN
  SELECT RAISE(ABORT, 'bornes estimation invalides');
END;

CREATE TRIGGER mesure_valeur_insert BEFORE INSERT ON mesure_indicateur
WHEN typeof(NEW.valeur) NOT IN ('integer', 'real')
BEGIN
  SELECT RAISE(ABORT, 'valeur mesure non numerique');
END;

CREATE TRIGGER mesure_valeur_update BEFORE UPDATE ON mesure_indicateur
WHEN typeof(NEW.valeur) NOT IN ('integer', 'real')
BEGIN
  SELECT RAISE(ABORT, 'valeur mesure non numerique');
END;
