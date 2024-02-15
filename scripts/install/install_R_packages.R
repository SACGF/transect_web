if (!require("BiocManager", quietly = TRUE))
    install.packages("BiocManager")

BiocManager::install("edgeR")
BiocManager::install("Glimma")
BiocManager::install("recount") # needed for RECOUNT3
BiocManager::install("recount3") # needed for RECOUNT3
BiocManager::install("DEFormats") # needed for RECOUNT3

install.packages("pacman")
install.packages("dplyr")
install.packages("tidyr")
install.packages("data.table")
install.packages("tibble")
install.packages("ggplot2")
install.packages("ggforce")
install.packages("calibrate")
install.packages("gplots")
install.packages("RColorBrewer")