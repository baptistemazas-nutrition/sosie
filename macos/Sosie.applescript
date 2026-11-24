on run
	set aide to POSIX path of (path to resource "sosie-app.sh")
	set versionSosie to do shell script quoted form of aide & " version"
	if versionSosie is "absent" then
		set r to display dialog ("sosie n'est pas encore installé sur ce Mac (ou son installation est abîmée)." & return & return & "L'installer maintenant ? Il faut une connexion Internet ; cela prend quelques minutes.") with title "Sosie" buttons {"Plus tard", "Installer"} default button "Installer" with icon caution
		if button returned of r is "Installer" then lancer(aide, {"reparer"})
		return
	end if
	set actions to {"Nouveau projet (première base de données)", "Ajouter de vraies données à un projet", "Refaire le sosie d'un projet", "Lancer un script sur les vraies données", "Vérifier les derniers résultats", "Ouvrir un projet dans VS Code", "Ouvrir le coffre d'un projet (vraies données)", "État et protection d'un projet", "Essayer avec des données d'exemple", "Mode d'emploi", "Réparer ou mettre à jour sosie"}
	set choix to choose from list actions with title "Sosie" with prompt (versionSosie & " — que veux-tu faire ?") default items {item 1 of actions} OK button name "Continuer" cancel button name "Quitter"
	if choix is false then return
	set choixFait to item 1 of choix
	if choixFait is item 1 of actions then
		nouveauProjet(aide)
	else if choixFait is item 2 of actions then
		ajouterDonnees(aide)
	else if choixFait is item 3 of actions then
		set racine to choisirProjet(aide, "Refaire le sosie de quel projet ? Sosie relit les vraies données du coffre.")
		if racine is not missing value then lancer(aide, {"creer", racine})
	else if choixFait is item 4 of actions then
		lancerScript(aide)
	else if choixFait is item 5 of actions then
		set racine to choisirProjet(aide, "Vérifier les derniers résultats de quel projet ?")
		if racine is not missing value then lancer(aide, {"verifier", racine})
	else if choixFait is item 6 of actions then
		set racine to choisirProjet(aide, "Ouvrir quel projet dans VS Code ?")
		if racine is not missing value then do shell script quoted form of aide & " ouvrir-vscode " & quoted form of racine
	else if choixFait is item 7 of actions then
		set racine to choisirProjet(aide, "Ouvrir le coffre de quel projet ? Ne le montre jamais à une IA.")
		if racine is not missing value then do shell script quoted form of aide & " ouvrir-coffre " & quoted form of racine
	else if choixFait is item 8 of actions then
		set racine to choisirProjet(aide, "État de quel projet ?")
		if racine is not missing value then lancer(aide, {"etat", racine})
	else if choixFait is item 9 of actions then
		set dossierParent to do shell script quoted form of aide & " dossier-projets"
		lancer(aide, {"exemple", dossierParent})
	else if choixFait is item 10 of actions then
		do shell script "open " & quoted form of (POSIX path of (path to resource "mode-emploi.html"))
	else if choixFait is item 11 of actions then
		lancer(aide, {"reparer"})
	end if
end run

on nouveauProjet(aide)
	set r to display dialog "Nom du nouveau projet (par exemple SEMASEARCH) :" default answer "" with title "Sosie — nouveau projet" buttons {"Annuler", "Continuer"} default button "Continuer" cancel button "Annuler"
	set nom to do shell script quoted form of aide & " nettoyer-nom " & quoted form of (text returned of r)
	if nom is "" then
		display dialog "Il faut un nom de projet." with title "Sosie" buttons {"OK"} default button "OK" with icon caution
		return
	end if
	set dossierParent to do shell script quoted form of aide & " dossier-projets"
	set r to display dialog ("Le dossier de travail du projet sera créé ici :" & return & return & dossierParent & "/" & nom & return & return & "C'est ce dossier que tu ouvriras dans VS Code pour travailler avec l'IA : il ne contiendra que le sosie (données fictives), tes scripts et les résultats vérifiés. Les vraies données iront dans le coffre.") with title "Sosie — nouveau projet" buttons {"Annuler", "Autre emplacement…", "Continuer"} default button "Continuer" cancel button "Annuler"
	if button returned of r is "Autre emplacement…" then
		set dossierChoisi to choose folder with prompt "Dans quel dossier créer le projet « " & nom & " » ?"
		set dossierParent to do shell script "p=" & quoted form of (POSIX path of dossierChoisi) & "; printf '%s' \"${p%/}\""
		do shell script quoted form of aide & " memoriser-dossier " & quoted form of dossierParent
	end if
	set fichiers to choisirDonnees("Où sont les vraies données de « " & nom & " » ?")
	set mode to "deplacer"
	if (count of fichiers) > 0 then set mode to choisirMode()
	lancer(aide, {"nouveau", nom, dossierParent, mode} & fichiers)
end nouveauProjet

on ajouterDonnees(aide)
	set racine to choisirProjet(aide, "À quel projet ajouter de vraies données ?")
	if racine is missing value then return
	set fichiers to choisirDonnees("Quelles vraies données ajouter ?")
	if (count of fichiers) is 0 then
		do shell script quoted form of aide & " ouvrir-donnees " & quoted form of racine
		display dialog "Le dossier des vraies données du projet est ouvert dans le Finder : dépose-y tes fichiers, puis choisis « Refaire le sosie d'un projet »." with title "Sosie" buttons {"OK"} default button "OK" with icon note
		return
	end if
	set mode to choisirMode()
	lancer(aide, {"ajouter", racine, mode} & fichiers)
end ajouterDonnees

on lancerScript(aide)
	set racine to choisirProjet(aide, "Dans quel projet est le script à lancer ?")
	if racine is missing value then return
	set invite to "Choisis le script à lancer sur les VRAIES données (R, Python, Quarto…) :"
	try
		set depart to (POSIX file (racine & "/scripts")) as alias
		set f to choose file with prompt invite default location depart
	on error msg number n
		if n is -128 then error number -128
		set f to choose file with prompt invite
	end try
	lancer(aide, {"executer", racine, POSIX path of f})
end lancerScript

on choisirDonnees(question)
	set r to display dialog (question & return & return & "Choisis le ou les fichiers (CSV, Excel, SAS, SPSS, Stata, Parquet, R…) ou le dossier qui les contient. Ils iront dans le coffre, que tu ne montreras jamais à l'IA.") with title "Sosie — vraies données" buttons {"Plus tard", "Un dossier…", "Des fichiers…"} default button "Des fichiers…" with icon note
	set b to button returned of r
	if b is "Plus tard" then return {}
	if b is "Un dossier…" then
		set d to choose folder with prompt "Choisis le dossier de tes vraies données :"
		return {POSIX path of d}
	end if
	set lesFichiers to choose file with prompt "Choisis le ou les fichiers de vraies données (⌘-clic pour en choisir plusieurs) :" with multiple selections allowed
	set chemins to {}
	repeat with f in lesFichiers
		set end of chemins to POSIX path of f
	end repeat
	return chemins
end choisirDonnees

on choisirMode()
	set r to display dialog ("Sosie va DÉPLACER ces données dans le coffre : de vraies données ne doivent exister qu'à un seul endroit, jamais montré à l'IA." & return & return & "Choisis « Copier » seulement si tu dois garder l'original où il est (pense à le supprimer ensuite).") with title "Sosie — vraies données" buttons {"Annuler", "Copier", "Déplacer"} default button "Déplacer" cancel button "Annuler" with icon note
	if button returned of r is "Copier" then return "copier"
	return "deplacer"
end choisirMode

on choisirProjet(aide, question)
	set lignes to paragraphs of (do shell script quoted form of aide & " lister")
	set noms to {}
	set chemins to {}
	set ancien to AppleScript's text item delimiters
	set AppleScript's text item delimiters to tab
	repeat with l in lignes
		set morceaux to text items of (l as text)
		if (count of morceaux) is greater than 1 then
			set end of noms to item 1 of morceaux
			set end of chemins to item 2 of morceaux
		end if
	end repeat
	set AppleScript's text item delimiters to ancien
	if (count of noms) is 0 then
		display dialog "Aucun projet pour l'instant : commence par « Nouveau projet »." with title "Sosie" buttons {"OK"} default button "OK" with icon note
		return missing value
	end if
	set choix to choose from list noms with title "Sosie" with prompt question default items {item 1 of noms} OK button name "Choisir" cancel button name "Annuler"
	if choix is false then return missing value
	repeat with i from 1 to count of noms
		if item i of noms is (item 1 of choix) then return item i of chemins
	end repeat
	return missing value
end choisirProjet

on lancer(aide, lesArguments)
	set ligne to "exec " & quoted form of aide
	repeat with a in lesArguments
		set ligne to ligne & " " & quoted form of (a as text)
	end repeat
	set contenu to "#!/bin/bash" & linefeed & "printf '\\033]0;Sosie\\007'" & linefeed & "clear" & linefeed & ligne & linefeed
	set dossierTmp to do shell script "mktemp -d \"${TMPDIR:-/tmp}/sosie.XXXXXX\""
	set fichier to dossierTmp & "/Sosie.command"
	do shell script "printf '%s' " & quoted form of contenu & " > " & quoted form of fichier & " && chmod 700 " & quoted form of fichier & " && open -a Terminal " & quoted form of fichier
end lancer
