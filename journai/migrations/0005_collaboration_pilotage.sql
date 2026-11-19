-- Socle F01 : registre des objets (chaînage et détection des orphelins), collaborations,
-- journal d'audit, notifications, indicateurs et mesures.
-- Le registre objet est la porte d'entrée unique des commentaires, abonnements,
-- événements et notifications : il permet de détecter un objet inconnu ou un parent manquant.

CREATE TABLE objet (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL REFERENCES espace(id) ON DELETE RESTRICT,
  type_objet TEXT NOT NULL CHECK (type_objet IN (
    'utilisateur', 'espace', 'structure', 'projet', 'public', 'canal', 'point_contact',
    'parcours', 'version_parcours', 'etape', 'transition_etape', 'occurrence_contact',
    'operation', 'ressource', 'constat', 'action', 'estimation_action', 'evaluation_action',
    'decision_priorite', 'indicateur', 'mesure_indicateur', 'commentaire')),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id)
);

CREATE TABLE commentaire (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  objet_id TEXT NOT NULL REFERENCES objet(id) ON DELETE RESTRICT,
  auteur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  commentaire_parent_id TEXT REFERENCES commentaire(id) ON DELETE RESTRICT,
  contenu TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  modifie_le TEXT,
  resolu_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  resolu_le TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  UNIQUE (id, espace_id),
  FOREIGN KEY (objet_id, espace_id) REFERENCES objet (id, espace_id) ON DELETE RESTRICT,
  CHECK (commentaire_parent_id IS NULL OR commentaire_parent_id <> id)
);

CREATE TABLE abonnement (
  objet_id TEXT NOT NULL REFERENCES objet(id) ON DELETE RESTRICT,
  utilisateur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  espace_id TEXT NOT NULL,
  niveau_notification TEXT NOT NULL CHECK (niveau_notification IN ('a', 'b', 'c')),
  PRIMARY KEY (objet_id, utilisateur_id),
  FOREIGN KEY (objet_id, espace_id) REFERENCES objet (id, espace_id) ON DELETE RESTRICT
);

-- Journal d'audit : F01 en fixe la structure minimale, F24 en complète l'usage.
CREATE TABLE evenement (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  objet_id TEXT NOT NULL,
  auteur_id TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  type_evenement TEXT NOT NULL CHECK (type_evenement IN ('cree', 'modifie', 'supprime', 'archive', 'restaure', 'commente', 'resout', 'notifie')),
  valeur_avant TEXT,
  valeur_apres TEXT,
  horodatage TEXT NOT NULL,
  UNIQUE (id, espace_id),
  FOREIGN KEY (objet_id, espace_id) REFERENCES objet (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE notification (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  destinataire_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  evenement_id TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  lu_le TEXT,
  UNIQUE (id, espace_id),
  FOREIGN KEY (evenement_id, espace_id) REFERENCES evenement (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE indicateur (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  projet_id TEXT,
  occurrence_contact_id TEXT,
  nom TEXT NOT NULL,
  definition TEXT NOT NULL,
  unite TEXT NOT NULL,
  mode_calcul TEXT NOT NULL CHECK (mode_calcul IN ('somme', 'moyenne', 'comptage', 'ratio', 'taux', 'manuel')),
  valeur_reference NUMERIC,
  valeur_cible NUMERIC,
  sens_amelioration TEXT NOT NULL CHECK (sens_amelioration IN ('croitre', 'decroitre', 'stable')),
  periodicite TEXT NOT NULL CHECK (periodicite IN ('quotidienne', 'hebdomadaire', 'mensuelle', 'trimestrielle', 'annuelle', 'ponctuelle')),
  responsable_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (espace_id, nom),
  FOREIGN KEY (projet_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (occurrence_contact_id, espace_id) REFERENCES occurrence_contact (id, espace_id) ON DELETE RESTRICT,
  -- Un indicateur porte au moins sur un projet, au moins sur une occurrence de contact, ou sur les deux.
  CHECK (projet_id IS NOT NULL OR occurrence_contact_id IS NOT NULL)
);

CREATE TABLE mesure_indicateur (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  indicateur_id TEXT NOT NULL,
  periode_debut TEXT NOT NULL,
  periode_fin TEXT NOT NULL,
  valeur NUMERIC NOT NULL,
  source TEXT NOT NULL,
  auteur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  niveau_confiance TEXT NOT NULL CHECK (niveau_confiance IN ('faible', 'moyenne', 'forte')),
  cree_le TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  UNIQUE (id, espace_id),
  UNIQUE (indicateur_id, periode_debut, periode_fin),
  FOREIGN KEY (indicateur_id, espace_id) REFERENCES indicateur (id, espace_id) ON DELETE RESTRICT,
  CHECK (periode_fin >= periode_debut)
);

-- Index des lectures décrites par les fiches F08, F09, F11, F15, F19, F20, F24.
CREATE INDEX ix_version_parcours_parcours ON version_parcours (parcours_id, perspective, numero);
CREATE INDEX ix_etape_version ON etape (version_parcours_id, ordre_affichage);
CREATE INDEX ix_transition_version ON transition_etape (version_parcours_id, etape_source_id);
CREATE INDEX ix_occurrence_etape ON occurrence_contact (etape_id, ordre_affichage);
CREATE INDEX ix_action_projet_statut ON action_projet (projet_id, espace_id);
CREATE INDEX ix_action_statut ON action (espace_id, statut, date_butoir);
CREATE INDEX ix_evenement_objet ON evenement (objet_id, horodatage);
CREATE INDEX ix_notification_destinataire ON notification (destinataire_id, lu_le, cree_le);
CREATE INDEX ix_commentaire_objet ON commentaire (objet_id, cree_le);
