-- Les gardes complètent la FK récursive sans reconstruire ni modifier les décisions.
CREATE TABLE controle_decisions_espace (
  valide INTEGER CONSTRAINT decisions_espaces_incoherents CHECK (valide = 1)
);
INSERT INTO controle_decisions_espace
SELECT 0 FROM decision_priorite successeur
JOIN decision_priorite predecesseur ON predecesseur.id = successeur.remplace_decision_id
WHERE successeur.espace_id <> predecesseur.espace_id
LIMIT 1;
DROP TABLE controle_decisions_espace;

CREATE TRIGGER decision_espace_insert BEFORE INSERT ON decision_priorite
WHEN EXISTS (
  SELECT 1 FROM decision_priorite predecesseur
  WHERE predecesseur.id = NEW.remplace_decision_id AND predecesseur.espace_id <> NEW.espace_id
) OR EXISTS (
  SELECT 1 FROM decision_priorite successeur
  WHERE successeur.remplace_decision_id = NEW.id AND successeur.espace_id <> NEW.espace_id
)
BEGIN
  SELECT RAISE(ABORT, 'decisions dans des espaces differents');
END;

CREATE TRIGGER decision_espace_update BEFORE UPDATE OF id, espace_id, remplace_decision_id ON decision_priorite
WHEN EXISTS (
  SELECT 1 FROM decision_priorite predecesseur
  WHERE predecesseur.id = NEW.remplace_decision_id AND predecesseur.id <> OLD.id
    AND predecesseur.espace_id <> NEW.espace_id
) OR EXISTS (
  SELECT 1 FROM decision_priorite successeur
  WHERE successeur.remplace_decision_id IN (OLD.id, NEW.id) AND successeur.id <> OLD.id
    AND successeur.espace_id <> NEW.espace_id
)
BEGIN
  SELECT RAISE(ABORT, 'decisions dans des espaces differents');
END;
