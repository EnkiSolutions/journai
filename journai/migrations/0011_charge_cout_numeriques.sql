-- Refuser les données historiques invalides sans les modifier.
CREATE TABLE controle_types_charges_couts (
  valide INTEGER CONSTRAINT types_charges_couts_invalides CHECK (valide = 1)
);
INSERT INTO controle_types_charges_couts
SELECT 0 FROM (
  SELECT charge_prevue_h AS valeur FROM contribution_action
  UNION ALL SELECT charge_realisee_h FROM contribution_action
  UNION ALL SELECT charge_min_h FROM estimation_action
  UNION ALL SELECT charge_probable_h FROM estimation_action
  UNION ALL SELECT charge_max_h FROM estimation_action
  UNION ALL SELECT cout_min FROM estimation_action
  UNION ALL SELECT cout_probable FROM estimation_action
  UNION ALL SELECT cout_max FROM estimation_action
)
WHERE typeof(valeur) NOT IN ('null', 'integer', 'real')
   OR abs(CAST(valeur AS REAL)) > 1.7976931348623157e308
LIMIT 1;
DROP TABLE controle_types_charges_couts;

CREATE TRIGGER contribution_types_insert BEFORE INSERT ON contribution_action
WHEN typeof(NEW.charge_prevue_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_prevue_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.charge_realisee_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_realisee_h AS REAL)) > 1.7976931348623157e308
BEGIN
  SELECT RAISE(ABORT, 'types charges couts invalides');
END;

CREATE TRIGGER contribution_types_update BEFORE UPDATE ON contribution_action
WHEN typeof(NEW.charge_prevue_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_prevue_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.charge_realisee_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_realisee_h AS REAL)) > 1.7976931348623157e308
BEGIN
  SELECT RAISE(ABORT, 'types charges couts invalides');
END;

CREATE TRIGGER estimation_types_insert BEFORE INSERT ON estimation_action
WHEN typeof(NEW.charge_min_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_min_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.charge_probable_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_probable_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.charge_max_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_max_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.cout_min) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.cout_min AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.cout_probable) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.cout_probable AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.cout_max) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.cout_max AS REAL)) > 1.7976931348623157e308
BEGIN
  SELECT RAISE(ABORT, 'types charges couts invalides');
END;

CREATE TRIGGER estimation_types_update BEFORE UPDATE ON estimation_action
WHEN typeof(NEW.charge_min_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_min_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.charge_probable_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_probable_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.charge_max_h) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.charge_max_h AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.cout_min) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.cout_min AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.cout_probable) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.cout_probable AS REAL)) > 1.7976931348623157e308
  OR typeof(NEW.cout_max) NOT IN ('null', 'integer', 'real')
  OR abs(CAST(NEW.cout_max AS REAL)) > 1.7976931348623157e308
BEGIN
  SELECT RAISE(ABORT, 'types charges couts invalides');
END;
