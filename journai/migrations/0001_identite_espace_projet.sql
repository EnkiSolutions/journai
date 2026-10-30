-- Socle F01 : identité, espaces, structures, projets.
-- Conventions (voir docs/adr/0001-architecture-et-contrat-api.md) :
-- identifiants UUID en texte, dates ISO-8601 en texte, clauses ON DELETE RESTRICT.
-- La colonne espace_id est reprise dans chaque table de relation et les clés étrangères
-- composites (id, espace_id) interdisent toute référence entre deux espaces différents.
-- L'exécution des clés étrangères exige PRAGMA foreign_keys = ON (posée par journai/db.py).

CREATE TABLE utilisateur (
  id TEXT NOT NULL PRIMARY KEY,
  nom_affiche TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  statut TEXT NOT NULL DEFAULT 'actif' CHECK (statut IN ('actif', 'inactif', 'suspendu')),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_le TEXT NOT NULL,
  modifie_le TEXT,
  archive_le TEXT
);

CREATE TABLE espace (
  id TEXT NOT NULL PRIMARY KEY,
  nom TEXT NOT NULL UNIQUE,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT
);

CREATE TABLE membre_espace (
  espace_id TEXT NOT NULL REFERENCES espace(id) ON DELETE RESTRICT,
  utilisateur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  role TEXT NOT NULL CHECK (role IN ('administrateur', 'contributeur', 'commentateur', 'lecteur')),
  statut TEXT NOT NULL DEFAULT 'actif' CHECK (statut IN ('actif', 'inactif')),
  PRIMARY KEY (espace_id, utilisateur_id)
);

CREATE TABLE structure (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL REFERENCES espace(id) ON DELETE RESTRICT,
  nom TEXT NOT NULL,
  type_structure TEXT NOT NULL CHECK (type_structure IN ('association', 'entreprise', 'collectivite', 'establishement', 'partenaire', 'autre')),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (espace_id, nom)
);

CREATE TABLE projet (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL REFERENCES espace(id) ON DELETE RESTRICT,
  structure_pilote_id TEXT NOT NULL,
  nom TEXT NOT NULL,
  finalite TEXT NOT NULL,
  statut TEXT NOT NULL DEFAULT 'prepare' CHECK (statut IN ('prepare', 'en_cours', 'suspendu', 'termine', 'abandonne')),
  responsable_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  date_debut TEXT,
  date_fin TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (espace_id, nom),
  FOREIGN KEY (structure_pilote_id, espace_id) REFERENCES structure (id, espace_id) ON DELETE RESTRICT,
  CHECK (date_fin IS NULL OR date_debut IS NULL OR date_fin >= date_debut)
);

-- Table d'association : structures associées à un projet, dans le même espace que le projet.
CREATE TABLE projet_structure (
  projet_id TEXT NOT NULL,
  structure_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  role_dans_projet TEXT NOT NULL CHECK (role_dans_projet IN ('pilote', 'co_pilote', 'partenaire', 'contributeur', 'observateur')),
  PRIMARY KEY (projet_id, structure_id),
  FOREIGN KEY (projet_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (structure_id, espace_id) REFERENCES structure (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE membre_projet (
  projet_id TEXT NOT NULL,
  utilisateur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  espace_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('pilote', 'contributeur', 'commentateur', 'lecteur')),
  capacite_hebdomadaire_h NUMERIC CHECK (capacite_hebdomadaire_h IS NULL OR capacite_hebdomadaire_h >= 0),
  PRIMARY KEY (projet_id, utilisateur_id),
  FOREIGN KEY (projet_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT
);
