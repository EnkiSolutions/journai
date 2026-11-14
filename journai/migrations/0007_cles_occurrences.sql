-- Refuser les doublons historiques sans modifier les données.
CREATE TABLE controle_cles_occurrences (
  valide INTEGER CONSTRAINT cles_occurrences_dupliquees CHECK (valide = 1)
);
INSERT INTO controle_cles_occurrences
SELECT 0 FROM occurrence_contact o
JOIN etape e ON e.id = o.etape_id
JOIN etape autre_etape ON autre_etape.version_parcours_id = e.version_parcours_id
JOIN occurrence_contact autre ON autre.etape_id = autre_etape.id
  AND autre.cle_stable = o.cle_stable AND autre.id <> o.id
LIMIT 1;
DROP TABLE controle_cles_occurrences;

CREATE INDEX ix_occurrence_cle_stable ON occurrence_contact (cle_stable, etape_id);

CREATE TRIGGER occurrence_cle_insert BEFORE INSERT ON occurrence_contact
WHEN EXISTS (
  SELECT 1 FROM occurrence_contact o
  LEFT JOIN etape existante ON existante.id = o.etape_id
  LEFT JOIN etape cible ON cible.id = NEW.etape_id
  WHERE o.cle_stable = NEW.cle_stable AND
    (o.etape_id = NEW.etape_id OR existante.version_parcours_id = cible.version_parcours_id)
)
BEGIN
  SELECT RAISE(ABORT, 'cle stable occurrence deja utilisee dans cette version');
END;

CREATE TRIGGER occurrence_cle_update BEFORE UPDATE OF id, etape_id, cle_stable ON occurrence_contact
WHEN EXISTS (
  SELECT 1 FROM occurrence_contact o
  LEFT JOIN etape existante ON existante.id = o.etape_id
  LEFT JOIN etape cible ON cible.id = NEW.etape_id
  WHERE o.id <> OLD.id AND o.cle_stable = NEW.cle_stable AND
    (o.etape_id = NEW.etape_id OR existante.version_parcours_id = cible.version_parcours_id)
)
BEGIN
  SELECT RAISE(ABORT, 'cle stable occurrence deja utilisee dans cette version');
END;

-- Une étape peut être insérée après ses occurrences si les FK sont différées.
CREATE TRIGGER etape_cles_occurrences_insert BEFORE INSERT ON etape
WHEN EXISTS (
  SELECT 1 FROM occurrence_contact o
  JOIN occurrence_contact autre ON autre.cle_stable = o.cle_stable AND autre.id <> o.id
  LEFT JOIN etape e ON e.id = autre.etape_id
  WHERE o.etape_id = NEW.id AND
    (autre.etape_id = NEW.id OR e.version_parcours_id = NEW.version_parcours_id)
)
BEGIN
  SELECT RAISE(ABORT, 'cle stable occurrence deja utilisee dans cette version');
END;

CREATE TRIGGER etape_cles_occurrences_update BEFORE UPDATE OF id, version_parcours_id ON etape
WHEN EXISTS (
  SELECT 1 FROM occurrence_contact o
  JOIN occurrence_contact autre ON autre.cle_stable = o.cle_stable AND autre.id <> o.id
  LEFT JOIN etape e ON e.id = autre.etape_id
  WHERE o.etape_id = NEW.id AND
    (autre.etape_id = NEW.id OR e.version_parcours_id = NEW.version_parcours_id)
)
BEGIN
  SELECT RAISE(ABORT, 'cle stable occurrence deja utilisee dans cette version');
END;
