-- Refuser les incohérences existantes avant de protéger les futures écritures.
CREATE TABLE controle_versions_courantes (
  valide INTEGER CONSTRAINT perspectives_courantes_incoherentes CHECK (valide = 1)
);
INSERT INTO controle_versions_courantes
SELECT 0 FROM parcours p
JOIN version_parcours v ON v.id = p.version_observee_id
WHERE v.perspective <> 'observee'
UNION ALL
SELECT 0 FROM parcours p
JOIN version_parcours v ON v.id = p.version_cible_id
WHERE v.perspective <> 'cible';
DROP TABLE controle_versions_courantes;

CREATE TRIGGER parcours_perspectives_insert BEFORE INSERT ON parcours
WHEN EXISTS (SELECT 1 FROM version_parcours v WHERE
  (v.id = NEW.version_observee_id AND v.perspective <> 'observee') OR
  (v.id = NEW.version_cible_id AND v.perspective <> 'cible'))
BEGIN
  SELECT RAISE(ABORT, 'perspective de version courante incorrecte');
END;

CREATE TRIGGER parcours_perspectives_update BEFORE UPDATE OF version_observee_id, version_cible_id ON parcours
WHEN EXISTS (SELECT 1 FROM version_parcours v WHERE
  (v.id = NEW.version_observee_id AND v.perspective <> 'observee') OR
  (v.id = NEW.version_cible_id AND v.perspective <> 'cible'))
BEGIN
  SELECT RAISE(ABORT, 'perspective de version courante incorrecte');
END;

-- Les références différées peuvent précéder l'insertion de leur version.
CREATE TRIGGER version_perspective_insert BEFORE INSERT ON version_parcours
WHEN EXISTS (SELECT 1 FROM parcours p WHERE
  (p.version_observee_id = NEW.id AND NEW.perspective <> 'observee') OR
  (p.version_cible_id = NEW.id AND NEW.perspective <> 'cible'))
BEGIN
  SELECT RAISE(ABORT, 'perspective de version courante incorrecte');
END;

CREATE TRIGGER version_perspective_update BEFORE UPDATE OF id, perspective ON version_parcours
WHEN EXISTS (SELECT 1 FROM parcours p WHERE
  (p.version_observee_id = NEW.id AND NEW.perspective <> 'observee') OR
  (p.version_cible_id = NEW.id AND NEW.perspective <> 'cible'))
BEGIN
  SELECT RAISE(ABORT, 'perspective de version courante incorrecte');
END;
