-- 1. Insert Regulations
INSERT INTO regulations (code, name, jurisdiction, applies_to_product_types)
VALUES 
('RoHS', 'Restriction of Hazardous Substances', 'EU', ARRAY['electronics']),
('REACH_SVHC', 'Registration, Evaluation, Authorisation and Restriction of Chemicals (SVHC)', 'EU', ARRAY['electronics', 'cosmetics', 'general_articles'])
ON CONFLICT (code) DO NOTHING;

-- 2. Insert RoHS Ingredients (10 substances)
INSERT INTO ingredients (canonical_name, cas_number)
VALUES
('Lead', '7439-92-1'),
('Mercury', '7439-97-6'),
('Cadmium', '7440-43-9'),
('Hexavalent chromium', '18540-29-9'),
('Polybrominated biphenyls (PBB)', '59536-65-1'),
('Polybrominated diphenyl ethers (PBDE)', '1163-19-5'),
('Bis(2-ethylhexyl) phthalate (DEHP)', '117-81-7'),
('Butyl benzyl phthalate (BBP)', '85-68-7'),
('Dibutyl phthalate (DBP)', '84-74-2'),
('Diisobutyl phthalate (DIBP)', '84-69-5')
ON CONFLICT (cas_number) DO NOTHING;

-- 3. Insert REACH SVHC Ingredients (20 recent substances)
INSERT INTO ingredients (canonical_name, cas_number)
VALUES
('Melamine', '108-78-1'),
('Isobutyl 4-hydroxybenzoate', '4247-02-3'),
('4,4''-sulphonyldiphenol (Bisphenol S)', '80-09-1'),
('Barium diboron tetraoxide', '13701-59-2'),
('N-(hydroxymethyl)acrylamide', '924-42-5'),
('6,6''-di-tert-butyl-2,2''-methylenedi-p-cresol', '119-47-1'),
('tris(2-methoxyethoxy)vinylsilane', '1067-53-4'),
('S-(tricyclo(5.2.1.0''2,6)deca-3-en-8(or 9)-yl O-(isopropyl or isobutyl or 2-ethylhexyl) O-(isopropyl or isobutyl or 2-ethylhexyl) phosphorodithioate', '255881-94-8'),
('4,4''-(1-methylpropylidene)bisphenol (Bisphenol B)', '77-40-7'),
('Glutaral', '111-30-8'),
('2-(4-tert-butylbenzyl)propionaldehyde and its individual stereoisomers', '80-54-6'),
('1,4-dioxane', '123-91-1'),
('Bis(2-(2-methoxyethoxy)ethyl) ether', '143-24-8'),
('Dioctyltin dilaurate, stannane, dioctyl-, bis(coco acyloxy) derivs.', '3648-18-8'),
('Dibutylbis(pentane-2,4-dionato-O,O'')tin', '22673-19-4'),
('2-methylimidazole', '693-98-1'),
('1-vinylimidazole', '1072-52-2'),
('Butyl 4-hydroxybenzoate', '94-26-8'),
('Perfluorobutane sulfonic acid (PFBS) and its salts', '375-73-5'),
('2-benzyl-2-dimethylamino-4''-morpholinobutyrophenone', '119313-12-1')
ON CONFLICT (cas_number) DO NOTHING;

-- 4. Insert RoHS Thresholds
INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2011-07-21', 'https://environment.ec.europa.eu/topics/waste-and-recycling/rohs-directive_en'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'RoHS' AND i.canonical_name IN (
    'Lead', 'Mercury', 'Hexavalent chromium', 'Polybrominated biphenyls (PBB)',
    'Polybrominated diphenyl ethers (PBDE)', 'Bis(2-ethylhexyl) phthalate (DEHP)',
    'Butyl benzyl phthalate (BBP)', 'Dibutyl phthalate (DBP)', 'Diisobutyl phthalate (DIBP)'
)
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.01, '%', '2011-07-21', 'https://environment.ec.europa.eu/topics/waste-and-recycling/rohs-directive_en'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'RoHS' AND i.canonical_name = 'Cadmium'
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

-- 5. Insert REACH SVHC Thresholds
INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2023-01-17', 'https://echa.europa.eu/candidate-list-table'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'REACH_SVHC' AND i.canonical_name IN (
    'Melamine', 'Isobutyl 4-hydroxybenzoate', '4,4''-sulphonyldiphenol (Bisphenol S)', 'Barium diboron tetraoxide'
)
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2022-06-10', 'https://echa.europa.eu/candidate-list-table'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'REACH_SVHC' AND i.canonical_name = 'N-(hydroxymethyl)acrylamide'
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2022-01-17', 'https://echa.europa.eu/candidate-list-table'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'REACH_SVHC' AND i.canonical_name IN (
    '6,6''-di-tert-butyl-2,2''-methylenedi-p-cresol', 'tris(2-methoxyethoxy)vinylsilane', 
    'S-(tricyclo(5.2.1.0''2,6)deca-3-en-8(or 9)-yl O-(isopropyl or isobutyl or 2-ethylhexyl) O-(isopropyl or isobutyl or 2-ethylhexyl) phosphorodithioate'
)
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2021-07-08', 'https://echa.europa.eu/candidate-list-table'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'REACH_SVHC' AND i.canonical_name IN (
    '4,4''-(1-methylpropylidene)bisphenol (Bisphenol B)', 'Glutaral', 
    '2-(4-tert-butylbenzyl)propionaldehyde and its individual stereoisomers', '1,4-dioxane'
)
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2021-01-19', 'https://echa.europa.eu/candidate-list-table'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'REACH_SVHC' AND i.canonical_name IN (
    'Bis(2-(2-methoxyethoxy)ethyl) ether', 'Dioctyltin dilaurate, stannane, dioctyl-, bis(coco acyloxy) derivs.'
)
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2020-06-25', 'https://echa.europa.eu/candidate-list-table'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'REACH_SVHC' AND i.canonical_name IN (
    'Dibutylbis(pentane-2,4-dionato-O,O'')tin', '2-methylimidazole', '1-vinylimidazole', 'Butyl 4-hydroxybenzoate'
)
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;

INSERT INTO regulation_thresholds (regulation_id, ingredient_id, threshold_value, threshold_unit, effective_date, source_url)
SELECT r.id, i.id, 0.1, '%', '2020-01-16', 'https://echa.europa.eu/candidate-list-table'
FROM regulations r CROSS JOIN ingredients i
WHERE r.code = 'REACH_SVHC' AND i.canonical_name IN (
    'Perfluorobutane sulfonic acid (PFBS) and its salts', '2-benzyl-2-dimethylamino-4''-morpholinobutyrophenone'
)
ON CONFLICT (regulation_id, ingredient_id, effective_date) DO NOTHING;
