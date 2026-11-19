-- Reconstruire commentaire risquerait ses références entrantes et la FK récursive.
-- Les triggers complètent la FK existante sans déplacer ni supprimer les données.
CREATE TABLE controle_commentaires_espace (
  valide INTEGER CONSTRAINT commentaires_espaces_incoherents CHECK (valide = 1)
);
INSERT INTO controle_commentaires_espace
SELECT 0 FROM commentaire enfant
JOIN commentaire parent ON parent.id = enfant.commentaire_parent_id
WHERE enfant.espace_id <> parent.espace_id
LIMIT 1;
DROP TABLE controle_commentaires_espace;

CREATE TRIGGER commentaire_espace_insert BEFORE INSERT ON commentaire
WHEN EXISTS (
  SELECT 1 FROM commentaire parent
  WHERE parent.id = NEW.commentaire_parent_id AND parent.espace_id <> NEW.espace_id
) OR EXISTS (
  SELECT 1 FROM commentaire enfant
  WHERE enfant.commentaire_parent_id = NEW.id AND enfant.espace_id <> NEW.espace_id
)
BEGIN
  SELECT RAISE(ABORT, 'commentaire parent et enfant dans des espaces differents');
END;

CREATE TRIGGER commentaire_espace_update BEFORE UPDATE OF id, espace_id, commentaire_parent_id ON commentaire
WHEN EXISTS (
  SELECT 1 FROM commentaire parent
  WHERE parent.id = NEW.commentaire_parent_id AND parent.id <> OLD.id
    AND parent.espace_id <> NEW.espace_id
) OR EXISTS (
  SELECT 1 FROM commentaire enfant
  WHERE enfant.commentaire_parent_id IN (OLD.id, NEW.id) AND enfant.id <> OLD.id
    AND enfant.espace_id <> NEW.espace_id
)
BEGIN
  SELECT RAISE(ABORT, 'commentaire parent et enfant dans des espaces differents');
END;
