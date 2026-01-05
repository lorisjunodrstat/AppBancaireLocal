CREATE TABLE plages_horaires (
    id INT AUTO_INCREMENT PRIMARY KEY,
    heure_travail_id INT NOT NULL,
    ordre INT NOT NULL,          -- 1 = h1, 2 = h2, 3 = h3, ...
    debut TIME,
    fin TIME,
    FOREIGN KEY (heure_travail_id) REFERENCES heures_travail(id) ON DELETE CASCADE,
    UNIQUE KEY unique_ordre (heure_travail_id, ordre)


