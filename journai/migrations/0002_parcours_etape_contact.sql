-- Socle F01 : publics, parcours versionnés, étapes, transitions, canaux et contacts.
-- Les clés étrangères composites verrouillent l'appartenance à un espace et,
-- pour les étapes et transitions, l'appartenance à une seule version de parcours.

CREATE TABLE public (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL REFERENCES espace(id) ON DELETE RESTRICT,
  parent_id TEXT,
  nom TEXT NOT NULL,
  role_interlocuteur TEXT NOT NULL CHECK (role_interlocuteur IN ('beneficiaire', 'aidant', 'relais', 'prescripteur', 'mandataire', 'porteur_structure', 'agent', 'autre')),
  description TEXT,
  criteres_segment TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (espace_id, parent_id, nom),
  FOREIGN KEY (parent_id, espace_id) REFERENCES public (id, espace_id) ON DELETE RESTRICT,
  CHECK (parent_id IS NULL OR parent_id <> id)
);

CREATE TABLE canal (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL REFERENCES espace(id) ON DELETE RESTRICT,
  nom TEXT NOT NULL,
  type_canal TEXT NOT NULL CHECK (type_canal IN ('physique', 'telephone', 'courriel', 'site_web', 'application', 'guichet', 'autre')),
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (espace_id, nom)
);

CREATE TABLE point_contact (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  projet_id TEXT NOT NULL,
  nom TEXT NOT NULL,
  -- Identité stable : le nom du point de contact ne dépend pas d'une occurrence.
  intention TEXT NOT NULL,
  responsable_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  FOREIGN KEY (projet_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE parcours (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  projet_id TEXT NOT NULL,
  nom TEXT NOT NULL,
  finalite TEXT NOT NULL,
  responsable_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  version_observee_id TEXT,
  version_cible_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  FOREIGN KEY (projet_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT,
  -- Les versions courantes d'un parcours sont des versions de ce parcours : référence circulaire
  -- autorisée par SQLite, vérifiée par PRAGMA foreign_key_check à la fin de la migration.
  FOREIGN KEY (version_observee_id, id) REFERENCES version_parcours (id, parcours_id) ON DELETE RESTRICT,
  FOREIGN KEY (version_cible_id, id) REFERENCES version_parcours (id, parcours_id) ON DELETE RESTRICT
);

CREATE TABLE parcours_public (
  parcours_id TEXT NOT NULL,
  public_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  PRIMARY KEY (parcours_id, public_id),
  FOREIGN KEY (parcours_id, espace_id) REFERENCES parcours (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (public_id, espace_id) REFERENCES public (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE version_parcours (
  id TEXT NOT NULL PRIMARY KEY,
  parcours_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  numero INTEGER NOT NULL CHECK (numero >= 1),
  perspective TEXT NOT NULL CHECK (perspective IN ('observee', 'cible')),
  statut TEXT NOT NULL DEFAULT 'brouillon' CHECK (statut IN ('brouillon', 'validee', 'abandonnee')),
  version_source_id TEXT,
  valide_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  valide_le TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, parcours_id),
  UNIQUE (id, espace_id),
  UNIQUE (parcours_id, perspective, numero),
  FOREIGN KEY (parcours_id, espace_id) REFERENCES parcours (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (version_source_id, parcours_id) REFERENCES version_parcours (id, parcours_id) ON DELETE RESTRICT,
  CHECK (version_source_id IS NULL OR version_source_id <> id),
  CHECK (valide_le IS NOT NULL OR statut = 'brouillon')
);

CREATE TABLE etape (
  id TEXT NOT NULL PRIMARY KEY,
  version_parcours_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  cle_stable TEXT NOT NULL,
  titre TEXT NOT NULL,
  objectif_public TEXT NOT NULL,
  condition_entree TEXT,
  condition_sortie TEXT,
  ordre_affichage INTEGER NOT NULL CHECK (ordre_affichage >= 0),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, version_parcours_id),
  UNIQUE (id, espace_id),
  UNIQUE (version_parcours_id, cle_stable),
  FOREIGN KEY (version_parcours_id, espace_id) REFERENCES version_parcours (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE transition_etape (
  id TEXT NOT NULL PRIMARY KEY,
  version_parcours_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  etape_source_id TEXT NOT NULL,
  etape_destination_id TEXT NOT NULL,
  condition_passage TEXT,
  ordre_affichage INTEGER NOT NULL CHECK (ordre_affichage >= 0),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (version_parcours_id, etape_source_id, etape_destination_id),
  FOREIGN KEY (version_parcours_id, espace_id) REFERENCES version_parcours (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (etape_source_id, version_parcours_id) REFERENCES etape (id, version_parcours_id) ON DELETE RESTRICT,
  FOREIGN KEY (etape_destination_id, version_parcours_id) REFERENCES etape (id, version_parcours_id) ON DELETE RESTRICT,
  CHECK (etape_source_id <> etape_destination_id)
);

CREATE TABLE occurrence_contact (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  etape_id TEXT NOT NULL,
  point_contact_id TEXT NOT NULL,
  canal_id TEXT NOT NULL,
  cle_stable TEXT NOT NULL,
  besoin_public TEXT NOT NULL,
  experience_attendue TEXT NOT NULL,
  criticite TEXT NOT NULL CHECK (criticite IN ('blocante', 'majeure', 'mineure', 'negligeable')),
  frequence TEXT NOT NULL CHECK (frequence IN ('ponctuelle', 'quotidienne', 'hebdomadaire', 'mensuelle', 'trimestrielle', 'annuelle', 'continue')),
  volume_estime INTEGER CHECK (volume_estime IS NULL OR volume_estime >= 0),
  etat_operationnel TEXT NOT NULL CHECK (etat_operationnel IN ('prevu', 'assure', 'non_assure', 'degrade', 'arrete')),
  ordre_affichage INTEGER NOT NULL CHECK (ordre_affichage >= 0),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (etape_id, point_contact_id, canal_id),
  FOREIGN KEY (etape_id, espace_id) REFERENCES etape (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (point_contact_id, espace_id) REFERENCES point_contact (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (canal_id, espace_id) REFERENCES canal (id, espace_id) ON DELETE RESTRICT
);
