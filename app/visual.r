VisualResume <- function(titles.left = c("Main Title", "Sub-title", "Sub-Sub-title"),
                        titles.left.cex = c(4, 2, 2),
                        titles.right = c("A", "B", "C"),
                        titles.right.cex = c(4, 3, 2),
                        timeline.labels = c("", ""),
                        timeline = NULL,
                        milestones = NULL,
                        events = NULL,
                        events.cex = 1.5,
                        langues = NULL,
                        langues.cex = 1.5,
                        skills = NULL,
                        skills.cex = 1.5,
                        font.family = NA,
                        col = NULL, # timeline$col,
                        trans,
                        year.steps = 1,
                        year.range = NULL,
                        langues.title.x,
                        langues.title.y,
                        langues.sub.x,
                        langues.sub.y,
                        coord1,
                        coord2,
                        coord3,
                        coord4,
                        image_link,
                        label.dir = NULL, # timeline$label.dir,
                        text.adj = NULL, # timeline$text.adj,
                        elbow = NULL, # timeline$elbow,
                        sub.cex = NULL, # timeline$sub.cex,
                        sub.font = NULL, # timeline$sub.font
                        matrix.widths,
                        heights.layout,
                        niveau.pourcent = NULL # langues$niveau.pourcent
) {
# --- Initialisation des valeurs par défaut dépendantes ---
{
    # Pour 'col'
    if (is.null(col) && !is.null(timeline) && "col" %in% names(timeline)) {
        col <- timeline$col
    } else if (is.null(col)) {
        col <- "gray80" # valeur de secours
    }

    # Pour label.dir, text.adj, elbow
    if (!is.null(timeline)) {
    if (is.null(label.dir) && "label.dir" %in% names(timeline)) label.dir <- timeline$label.dir
    if (is.null(text.adj) && "text.adj" %in% names(timeline)) text.adj <- timeline$text.adj
    if (is.null(elbow) && "elbow" %in% names(timeline)) elbow <- timeline$elbow
    if (is.null(sub.cex) && "sub.cex" %in% names(timeline)) sub.cex <- timeline$sub.cex
    if (is.null(sub.font) && "sub.font" %in% names(timeline)) sub.font <- timeline$sub.font
    }

    # Valeurs par défaut de secours si toujours NULL
    if (is.null(label.dir)) label.dir <- "right"
    if (is.null(text.adj)) text.adj <- 0
    if (is.null(elbow)) elbow <- 0.2
    if (is.null(sub.cex)) sub.cex <- 0.9
    if (is.null(sub.font)) sub.font <- 1

    # Pour niveau.pourcent
    if (is.null(niveau.pourcent) && !is.null(langues) && "niveau.pourcent" %in% names(langues)) {
        niveau.pourcent <- langues$niveau.pourcent
        }
    # Convert factors to strings

    if (!is.null(timeline) && ncol(timeline) > 0) {
        for (i in 1:ncol(timeline)) {
            if (class(timeline[, i]) == "factor") {
                timeline[, i] <- as.character(timeline[, i])
                }
            }
        }

    # Extract some parameters
    events.selected <- if (!is.null(events) && nrow(events) > 0) 1:nrow(events) else integer(0)
    langues.selected <- if (!is.null(langues) && nrow(langues) > 0) 1:nrow(langues) else integer(0)
    skills.selected <- if (!is.null(skills) && nrow(skills) > 0) 1:nrow(skills) else integer(0)
    top.graph.label <- timeline.labels[1]
    bottom.graph.label <- timeline.labels[2]
    }
## Colors and Fonts
{
    if (font.family %in% sysfonts::font.families.google()) {
        google.font <- TRUE
        sysfonts::font.add.google(font.family, font.family)
        showtext::showtext.begin()
    } else {
    font.family <- "Helvetica"
    google.font <- FALSE
    }

    n_timeline <- if (!is.null(timeline)) nrow(timeline) else 0

    if (n_timeline == 0) {
        stop("Erreur : 'timeline' ne peut pas être NULL ou vide")
    }

    if (length(col) == n_timeline) {
        color.vec <- col
    } else {
        color.vec <- col
        
        # Make colors transparent
        for (i in 1:length(color.vec)) {
            col.o <- grDevices::col2rgb(col = color.vec[i])
            col.n <- grDevices::rgb(red = col.o[1], green = col.o[2], blue = col.o[3], alpha = trans * 255, maxColorValue = 255)
            color.vec[i] <- col.n
        }
    }


    if (length(color.vec) < (nrow(timeline))) {
        color.vec <- rep(color.vec, length.out = (nrow(timeline)))
        }
    }


# Get year range

{
    if (is.null(year.range)) {
        if (is.null(timeline) || is.null(timeline$start) || is.null(timeline$end)) {
            stop("Erreur : 'timeline' doit contenir les colonnes 'start' et 'end'")
            }
        year.range <- c(
            floor(min(timeline$start, na.rm = TRUE)),
            ceiling(max(timeline$end, na.rm = TRUE))
        )

        year.min <- min(year.range)
        year.max <- max(year.range)


        year.seq <- seq(min(year.range), max(year.range), by = year.steps)

        if (max(year.seq) != year.max) {
            year.seq <- c(year.seq, max(year.seq) + year.steps)
            
            year.min <- min(year.seq)
            year.max <- max(year.seq)
        }
    }
}
# Plot Layout
{
    layout(
        matrix(c(1, 1, 1, 2, 2, 2, 3, 4, 5), nrow = 3, ncol = 3, byrow = TRUE),
        widths = matrix.widths,
        heights = heights.layout
        )
}


# ----------------
# Header
# ----------------
{
    par(mar = c(0, 00, 0, 0))

    plot(1, xlim = c(0, 1), ylim = c(0, 1), bty = "n", type = "n", xaxt = "n", yaxt = "n", ylab = "", xlab = "")
    rect(xleft = -2, ybottom = -10, xright = 0.06 + 0.048, ytop = 1.5, col = "#F9B90A99", lwd = 0)

    rect(xleft = 0.06 + 0.048, ybottom = -10, xright = 2, ytop = 1.5, col = "#E6352F99", lwd = 0, border = NA)
    rasterImage(png::readPNG(image_link), coord1, coord2, coord3, coord4, interpolate = TRUE)
    # Left and Right header titles
    text(rep(.18, 1), c(.65, .45), titles.left, adj = 0, cex = titles.left.cex, font = c(2, 1), family = "Helvetica Neue")
    text(rep(0.98, 1), c(.6, .45, .3), titles.right, adj = 1, cex = titles.right.cex, font = c(1, 1, 1), family = "Helvetica")
}

# ----------------
# Body
# ----------------
{
    par(mai = c(0, 0, 0, 0), bg = "white")
    # Minimum values of top and bottom
    top.y0 <- 52
    bottom.y0 <- 48
    # Adjust simultaneous starting times
    if (nrow(timeline) > 1) {
        for (i in 2:nrow(timeline)) {
            if (timeline$start[i] %in% timeline$start[1:(i - 1)]) {
                timeline$start[i] <- timeline$start[i] + 0.1
                }
            }
        }
    plot(1,
        xlim = c(year.min - 2, year.max + 3),
        ylim = c(0, 100), type = "n", xaxt = "n",
        yaxt = "n", ylab = "", xlab = "",
        bty = "n"
        )
    rect(xleft = year.min - 200, ybottom = -50, xright = 2005.6, ytop = 150, col = "#11111111", lwd = 0, border = NA)
    rect(xleft = 2025, ybottom = -50, xright = 2040, ytop = 150, col = "#11111111", lwd = 0, border = NA)


    abline(a = year.min - 5, b = year.min, h = 50)
    abline(a = year.max, b = year.max + 5, h = 50)
    ## Year labels
    segments(year.seq,
        rep(bottom.y0, length(year.seq)),
        year.seq,
        rep(top.y0, length(year.seq)),
        col = "black"
        )
    if (length(year.seq) > 1) {
        rect(
            xleft = year.seq[-length(year.seq)], # années 1 à n-1
            ybottom = rep(bottom.y0, length(year.seq) - 1),
            xright = year.seq[-1], # années 2 à n
            ytop = rep(top.y0, length(year.seq) - 1),
            col = "white",
            border = gray(0.2),
            lwd = 1
        )
    }

    text(
        x = year.seq[2:length(year.seq)] - (year.seq[2] - year.seq[1]) / 2,
        y = rep(50, length(year.seq) - 1),
        labels = year.seq[-(length(year.seq))],
        cex = .9, family = "Helvetica"
    )

    text(year.min - 2.5, 55, top.graph.label, family = "Helvetica", cex = 1.3, adj = 0, font = 3)
    text(year.min - 2.5, 40, bottom.graph.label, family = "Helvetica", cex = 1.3, adj = 0, font = 3)

    # Determine coordinates..

    #  -------
    # BOX COORDINATES
    #  --------
    {
        change.box.x0 <- FALSE
        change.box.x1 <- FALSE
        change.box.y0 <- FALSE
        change.box.y1 <- FALSE
        
        if ("box.x0" %in% names(timeline) == FALSE) {
            timeline$box.x0 <- NA
            change.box.x0 <- TRUE
            }
    
        if ("box.y0" %in% names(timeline) == FALSE) {
            timeline$box.y0 <- NA
            change.box.y0 <- TRUE
            }
        
        if ("box.x1" %in% names(timeline) == FALSE) {
            timeline$box.x1 <- NA
            change.box.x1 <- TRUE
            }
        
        if ("box.y1" %in% names(timeline) == FALSE) {
            timeline$box.y1 <- NA
            change.box.y1 <- TRUE
            }
    
        for (i in 1:nrow(timeline)) {
            # Get default locations
            if (is.na(timeline$box.x0[i])) {
                side.i <- timeline$side[i]
                box.x0 <- timeline$start[i]
                box.y0 <- switch(paste(side.i),
                                "0" = 48,
                                "1" = 52
                            )
                box.x1 <- timeline$end[i]
                
                box.y1 <- switch(paste(side.i),
                                "0" = box.y0 - 8,
                                "1" = box.y0 + 8
                            )
                # Am I starting at the same time as a previous box?
            
                simultaneous.boxes <- sum(
                    timeline$box.x0[1:(i - 1)] == box.x0 &
                    timeline$side[1:(i - 1)] == side.i,
                    na.rm = TRUE
                    )
                if (simultaneous.boxes > 0) {
                    box.x0 <- box.x0 + .1 * simultaneous.boxes
                    }
                
                # Am I starting within a previous box?
                
                existing.boxes <- sum(timeline$box.x0[-i] < box.x0 &
                                        timeline$box.x1[-i] > box.x0 &
                                        timeline$side[-i] == side.i, na.rm = TRUE)
                
                box.y1 <- box.y1 + existing.boxes * switch(paste(side.i),
                                                            "0" = -4,
                                                            "1" = 4
                            )
                
                if (change.box.x0) {
                    timeline$box.x0[i] <- box.x0
                    }
                if (change.box.x1) {
                    timeline$box.x1[i] <- box.x1
                    }
                if (change.box.y0) {
                    timeline$box.y0[i] <- box.y0
                    }
                if (change.box.y1) {
                    timeline$box.y1[i] <- box.y1
                    }
            }
        }
    }

#  -------
# POINT COORDINATES
#  --------
    {
        change.point.x <- FALSE
        change.point.y <- FALSE
        
        if ("point.x" %in% names(timeline) == FALSE) {
        change.point.x <- TRUE
        timeline$point.x <- NA
        }
        
        if ("point.y" %in% names(timeline) == FALSE) {
        change.point.y <- TRUE
        timeline$point.y <- NA
        }
        
        for (i in 1:nrow(timeline)) {
        side.i <- timeline$side[i]
        
        # Get default locations
        
        # Does another box start in this box?
        
        conflicting.l <- timeline$start[-i] > timeline$start[i] & timeline$start[-i] < timeline$end[i] & timeline$side[i] == timeline$side[-i]
        
        if (any(conflicting.l) == FALSE) {
            point.x <- timeline$start[i] + .5 * (timeline$end[i] - timeline$start[i])
            point.y <- timeline$box.y0[i] + switch(paste(side.i),
                                                    "0" = -5,
                                                    "1" = 5
            )
        }
        
        if (any(conflicting.l)) {
            next.start <- min(timeline$start[-i][conflicting.l])
            
            point.x <- timeline$start[i] + .5 * (next.start - timeline$start[i])
            point.y <- timeline$box.y0[i] + switch(paste(side.i),
                                                    "0" = -5,
                                                    "1" = 5
            )
        }
        
        # Is there another point in the same location?
        
        points.conflicting <- sum(abs(timeline$point.x[-i] - point.x) < .1 &
                                    (timeline$point.y[-i] - point.y) < .1, na.rm = TRUE)
        
        if (any(points.conflicting)) {
            point.x <- point.x + sum(points.conflicting) * .1
            point.y <- point.y + sum(points.conflicting)
        }
        
        if (change.point.x) {
            timeline$point.x[i] <- point.x
        }
        if (change.point.y) {
            timeline$point.y[i] <- point.y
        }
        }
    }


#  -------
# LABEL COORDINATES
#  --------
{
    change.label.dir <- TRUE
    change.text.adj <- FALSE
    change.elbow <- FALSE
    change.label.x <- FALSE
    change.label.y <- FALSE
    if ("label.dir" %in% names(timeline) == FALSE) {
        change.label.dir <- TRUE
        timeline$label.dir <- NA
        }
    if ("text.adj" %in% names(timeline) == FALSE) {
        timeline$text.adj <- NA
        change.text.adj <- TRUE
        }
    if ("elbow" %in% names(timeline) == FALSE) {
        timeline$elbow <- NA
        change.elbow <- TRUE
        }
    if ("label.x" %in% names(timeline) == FALSE) {
        timeline$label.x <- NA
        change.label.x <- TRUE
        }
    if ("label.y" %in% names(timeline) == FALSE) {
        timeline$label.x <- NA
        change.label.y <- TRUE
        }
    for (i in 1:nrow(timeline)) {
        method <- 2
    
        if (is.na(timeline$label.x[i])) {
            if (method == 1) {
            side.i <- timeline$side[i]
            label.x <- timeline$point.x[i]
        
        # Do other boxes start within x percent of the timeline on the right or left?
        
        scare.p <- .1
        scare.dist <- scare.p * diff(year.range)
        
        right.conflicting.l <- (timeline$start[-i] >= timeline$start[i]) & (timeline$start[-i] <= timeline$start[i] + scare.dist) & (timeline$side[-i] == side.i)
        left.conflicting.l <- timeline$start[-i] <= timeline$start[i] & (timeline$start[-i] >= timeline$start[i] - scare.dist) & (timeline$side[-i] == side.i)
        
        # If there are no conflicts, go right
        
        if (any(right.conflicting.l) == FALSE &
            any(left.conflicting.l) == FALSE) {
                label.y <- timeline$box.y1[i] + switch(paste(side.i),
                                                    "0" = -5,
                                                    "1" = 5)
                label.dir <- "right"
                text.adj <- 0
                elbow <- .3
                }
        
        
        # If there are more right than left conflicts then go left
        
        if (sum(right.conflicting.l) > sum(left.conflicting.l)) {
            conflicting.box.heights <- timeline$box.y1[-i][left.conflicting.l | right.conflicting.l]
            conflicting.label.heights <- timeline$label.y[-i][left.conflicting.l | right.conflicting.l]
            
            if (side.i == 1) {
                label.y <- max(c(conflicting.box.heights, timeline$box.y1[i], conflicting.label.heights)) + 10
                } 
            if (side.i == 0) {
                label.y <- min(c(conflicting.box.heights, timeline$box.y1[i], conflicting.label.heights)) - 10
                }
            label.dir <- "left"
            text.adj <- 1
            elbow <- -.1
            }
        
        # If there are more left than right conflicts
        
        if (sum(right.conflicting.l) <= sum(left.conflicting.l)) {
            conflicting.box.heights <- timeline$box.y1[-i][right.conflicting.l]
            conflicting.label.heights <- timeline$label.y[-i][right.conflicting.l]
            if (side.i == 1) {
                label.y <- max(c(conflicting.box.heights, timeline$box.y1[i], conflicting.label.heights)) + 5
                } 
            if (side.i == 0) {
                label.y <- min(c(conflicting.box.heights, timeline$box.y1[i], conflicting.label.heights)) - 5
                }
            
            label.dir <- "right"
            text.adj <- 0
            elbow <- .1
            }
        
        # Are there any long labels on the left?
        
        if (i > 1) {
            label.conflict.l <- (timeline$point.x[-i] - timeline$point.x[i]) > -scare.dist &
            (timeline$point.x[-i] - timeline$point.x[i]) < 0 &
            nchar(timeline$title[-i]) > 8 &
            timeline$label.dir[-i] == "right" &
            timeline$side[-i] == side.i
            
            if (any(label.conflict.l)) {
                label.y <- label.y + 4 * sum(label.conflict.l)
                }
            }
        }
        if (method == 2) {
            # Grid method
        
            side.i <- timeline$side[i]
            point.x <- timeline$point.x[i]
            box.y <- timeline$box.y1[i]
            
            x.loc <- c(point.x)
            
            if (side.i == 1) {
                y.loc <- seq(box.y, 90, length.out = 10)
                }
            if (side.i == 0) {
                y.loc <- seq(box.y, 10, length.out = 10)
                }
        
            location.mtx <- expand.grid(x = x.loc, y = y.loc)
        
            # Assign initial points
            
            x.dev <- abs(location.mtx$x - point.x)
        
            if (timeline$side[i] == 1) {
                y.dev <- abs(location.mtx$y - (box.y + 10))
            }
            
            if (timeline$side[i] == 0) {
                y.dev <- abs(location.mtx$y - (box.y - 10))
            }
            
            joint.dev <- x.dev + y.dev
            
            if (i == 1) {
                which.min <- which(joint.dev == min(joint.dev))
                
                label.x <- location.mtx$x[which.min]
                label.y <- location.mtx$y[which.min]
                label.dir <- "right"
                text.adj <- 0
                elbow <- .1
            }
            
            if (i > 1) {
                for (j in 1:(i - 1)) {
                if (timeline$side[j] == timeline$side[i]) {
                    other.x.loc <- timeline$label.x[j]
                    other.y.loc <- timeline$label.y[j]
                    
                    # Are there other labels within scare.p years?
                    
                    scare.p <- .3
                    scare.d <- scare.p * diff(year.range)
                    
                    x.dev.l <- abs(other.x.loc - location.mtx$x) < scare.d
                    
                    x.dev <- x.dev + as.numeric(x.dev.l)
                    
                    y.dev[x.dev.l] <- y.dev[x.dev.l] + as.numeric(abs(other.y.loc - location.mtx$y[x.dev.l]) < 5) * 10
                }
                }
            
            
            joint.dev <- x.dev + y.dev
            which.min <- which(joint.dev == min(joint.dev))
            
            label.x <- location.mtx$x[which.min][1]
            label.y <- location.mtx$y[which.min][1]
            
            # Determine label direction
            
            # Is there a previous right direction label within 2 years?
            
            scare.p <- .1
            scare.d <- scare.p * diff(year.range)
            
            # Potentially conflicting blocks on left
            l.conflicting.l <- any(timeline$side[1:(i - 1)] == timeline$side[i] &
                                    timeline$point.x[1:(i - 1)] > (timeline$point.x[i] - scare.d))
            
            # Is everything clear on the right for the next scare.d?
            side.i <- timeline$side[i]
            point.x.i <- timeline$point.x[i]
            
            r.free.l <- nrow(subset(
            timeline[-i, ],
            side == side.i &
                point.x > point.x.i & point.x < (point.x.i + scare.d)
            )) == 0
            
            if (l.conflicting.l | r.free.l) {
            label.dir <- "right"
            text.adj <- 0
            elbow <- .2
            } else {
            label.dir <- "left"
            text.adj <- 1
            elbow <- -.1
            }
        }
        }
    }
    
    # Write values
    if (change.label.y) {
        timeline$label.y[i] <- label.y
    }
    if (change.label.x) {
        timeline$label.x[i] <- label.x
    }
    if (change.label.dir) {
        timeline$label.dir[i] <- label.dir
    }
    if (change.text.adj) {
        timeline$text.adj[i] <- text.adj
    }
    if (change.elbow) {
        timeline$elbow[i] <- elbow
    }
    }
}

# Draw!

for (i in 1:nrow(timeline)) {
    # Box
    rect(
        xleft = timeline$box.x0[i],
        ybottom = timeline$box.y0[i],
        xright = timeline$box.x1[i],
        ytop = timeline$box.y1[i],
        col = color.vec[i],
        border = NULL,
        lwd = 0
        )
    # Points
    points(
        timeline$point.x[i] + 5,
        timeline$point.y[i],
        pch = 21,
        cex = 1,
        col = "white",
        bg = "white"
        )
    # Add lines
    
    # Main line
    segments(
        timeline$point.x[i],
        timeline$point.y[i],
        timeline$label.x[i],
        timeline$label.y[i],
        col = "black",
        lty = 3
        )
    
    # Elbow line
    segments(
        timeline$label.x[i],
        timeline$label.y[i],
        timeline$label.x[i] + timeline$elbow[i],
        timeline$label.y[i],
        col = "black",
        lty = 3
        )
    # Rect
    # if (timeline$label.dir[i] == "right" ) {
    # rect(xleft = timeline$label.x[i] + timeline$elbow[i] + .1 - 2,
    #    ybottom = timeline$label.y[i] - 5 ,
    #     xright = timeline$label.x[i] + timeline$elbow[i] + .1 + 2,
    #     ytop = timeline$label.y[i] + 2.5,
    #    col = "white")
    # }
    # else {
    
    # rect(xleft = timeline$label.x[i] + timeline$elbow[i] + .1 - 2,
    #    ybottom = timeline$label.y[i] - 5 ,
    #    xright = timeline$label.x[i] + timeline$elbow[i] + .1 + 2,
    #    ytop = timeline$label.y[i] + 2.5,
    #    col = "white")
    # }
    # Main Text
    if (timeline$label.dir[i] == "right") {
        text(
            timeline$label.x[i] + timeline$elbow[i] + .1,
            timeline$label.y[i],
            adj = timeline$text.adj[i],
            labels = timeline$title[i],
            cex = 1.2,
            family = "Helvetica",
            font = 2,
            col = "black",
            bg = "white"
            )
    } else {
        text(
            timeline$label.x[i] + timeline$elbow[i] - .1,
            timeline$label.y[i],
            adj = timeline$text.adj[i],
            labels = timeline$title[i],
            cex = 1.2,
            family = "Helvetica",
            font = 2,
            col = "black",
            bg = "white"
            )
    }
    
    
    # text.outline(timeline$label.x[i] + timeline$elbow[i],
    #              timeline$label.y[i],
    #             adj = timeline$text.adj[i],
    #            labels = timeline$title[i],
    #           cex = 1.8,
    #          family = font.family,
    #         bg = black(.97, .5),
    #        h = 1
    #       w = (year.max - year.min) / 100,
    # )
    
    # Sub Text
    if (nchar(paste(as.character(timeline[i, 2]))) > 30 & nchar(paste(as.character(timeline[i, 2]))) < 60) {
        text(
            timeline$label.x[i] + timeline$elbow[i],
            timeline$label.y[i] - 4.5,
            adj = timeline$text.adj[i],
            labels = gsub("(.{25}?)\\s", "\\1\n", timeline$sub[i]),
            cex = timeline$sub.cex[i],
            font = timeline$sub.font[i],
            family = "Helvetica"
        )
    } else if (nchar(paste(as.character(timeline[i, 2]))) > 60) {
    text(
        timeline$label.x[i] + timeline$elbow[i],
        timeline$label.y[i] - 5.5,
        adj = timeline$text.adj[i],
        labels = gsub("(.{30}?)\\s", "\\1\n", timeline$sub[i]),
        cex = timeline$sub.cex[i],
        font = timeline$sub.font[i],
        family = "Helvetica",
        col = "black",
        bg = "white"
        )
    } else {
        text(
            timeline$label.x[i] + timeline$elbow[i],
            timeline$label.y[i] - 3,
            adj = timeline$text.adj[i],
            labels = timeline$sub[i],
            cex = timeline$sub.cex[i],
            font = timeline$sub.font[i],
            family = "Helvetica",
            col = "black",
            bg = "white"
            )
    }
}

# --------- Upper milestones
if (!is.null(milestones) && nrow(milestones) > 0) {
    text(milestones$year,
        rep(95, nrow(milestones)),
        milestones$title,
        cex = 1.8, adj = 0.5, family = "Helvetica", font = 3
    )
    
    text(milestones$year,
        rep(90, nrow(milestones)),
        milestones$sub,
        cex = 1.2, adj = 0.5, family = "Helvetica", font = 1
    )
}


# ----------------
# Bottom
# ----------------
# ---- Bottom left langues
{
    par(mar = c(0, 0, 0, 0))
    
    # Setup plotting region
    # layout(mat = matrix(c(0, 0, 0,
    #                     0,1,0,
    #                    0,0,0),
    #                 nrow = 3,
    #                ncol = 3),
    #  heights = c(0.1,0.8,0.1),    # Heights of the two rows
    # widths = c(0.1,0.8,0.1))
    # plot.window(xlim = c(0,4), ylim = range(langues$niveau.pourcent))
    plot(
        0, 0,
        xlim = c(0, 1), ylim = c(0, 1), xaxt = "n", yaxt = "n",
        bty = "n", type = "n", xlab = "", ylab = "", log = ""
    )
    
    rect(xleft = -2, ybottom = 0.9, xright = 3, ytop = 1.5, col = "#E6352F99", lwd = 0, border = NA)
    text(0.2, 0.97, "Compétences linguistiques", family = "Helvetica", cex = 1.3, adj = 0, font = 3)
    # barplot(langues$niveau.pourcent, horiz=TRUE,
    #    names.arg=c("Français", "Anglais", "Allemand", "Chinois"),
    #   col=c("#3D79F399", "#F9B90A99","#34A74B99","#E6352F99"),
    # las = 1, add = TRUE)
    ##  axes = F, cex.axis=0.2,
    
    text(0.25, 0.775, "Français", family = "Helvetica", cex = 1, adj = 1, font = 2)
    rect(
        xleft = 0.3,
        ybottom = 0.75,
        xright = 0.3 + 1 * (.9 - 0.3),
        ytop = 0.8,
        col = "#3D79F399",
        border = NULL,
        lwd = 0
        )
    
    
    text(0.25, 0.625, "Allemand", family = "Helvetica", cex = 1, adj = 1, font = 2)
    rect(
        xleft = 0.3,
        ybottom = 0.6,
        xright = 0.3 + 0.6 * (.9 - 0.3),
        ytop = 0.65,
        col = "#F9B90A99",
        border = NULL,
        lwd = 0
        )
    text(0.72, 0.625, "B2", family = "Helvetica", cex = 1, adj = 1, font = 2)
    
    text(0.25, 0.475, "Anglais", family = "Helvetica", cex = 1, adj = 1, font = 2)
    rect(
        xleft = 0.3,
        ybottom = 0.45,
        xright = 0.3 + 0.8 * (.9 - 0.3),
        ytop = 0.5,
        col = "#34A74B99",
        border = NULL,
        lwd = 0
        )
    text(0.85, 0.475, "C1", family = "C1", cex = 1, adj = 1, font = 2)
    
    text(0.25, 0.325, "Chinois", family = "Helvetica", cex = 1, adj = 1, font = 2)
    rect(
        xleft = 0.3,
        ybottom = 0.3,
        xright = 0.3 + 0.3 * (.9 - 0.3),
        ytop = 0.35,
        col = "#E6352F99",
        border = NULL,
        lwd = 0
        )
    text(0.6, 0.325, "HSK 2", family = "Helvetica", cex = 1, adj = 1, font = 2)
    # rasterImage(png::readPNG("graph.png"),0.2,0.2,0.9,.9, interpolate = TRUE)
    
    # Top label text
    # mtext(bottom.labels[3], side = 3, cex = 1.5, adj = .5, family = font.family)
    
    
    # n.langues <- length(langues.selected)
    
    
    # Event text
    
    # text(langues.title.x,
    #      langues.title.y,
    #     langues[1:nrow(langues) %in% langues.selected,1],
    #     adj = 0, cex = langues.cex, family = "Helvetica", font = 2)
    # Original
    
    # text(rep(.1, 2),
    #    seq(.9, .1, length.out = 4),
    #   langues[1:nrow(langues) %in% langues.selected,2],
    #  adj = 0, cex = langues.cex, family = "Helvetica", font = 2)
    # text(langues.sub.x,
    #     langues.sub.y,
    #    langues[1:nrow(langues) %in% langues.selected,2],
    #   adj = 0, cex = (langues.cex), family = "Helvetica", font = 1
    # )
}
# ---- Bottom center skills
{
    par(mar = c(0, 0, 0, 0))
    
    
    plot(0, 1,
        xlim = c(0, 2), ylim = c(0, 1), xaxt = "n", yaxt = "n",
        bty = "n", type = "n", xlab = "", ylab = ""
    )
    
    rect(xleft = -2, ybottom = 0.9, xright = 3, ytop = 1.5, col = "#3D79F399", lwd = 0, border = NA)
    text(0.2, 0.97, "Compétences organisationnelles / techniques", family = "Helvetica", cex = 1.3, adj = 0, font = 3)
    
    # Top label text
    # mtext(bottom.labels[3], side = 3, cex = 1.2, adj = .5, family = font.family)
    
    n.skills <- length(skills.selected)
    
    # Points
    #    points(rep(-0.1, n.skills), seq(.85, .1, length.out = n.skills), pch = 0, cex = 3.5, col = "red", bg = "white")
    
    # Event text
    text(rep(.05, n.skills),
        seq(.85, .25, length.out = n.skills),
        skills[1:nrow(skills) %in% skills.selected, 2],
        adj = 0, cex = skills.cex, family = "Helvetica", font = 1.5
    )
    text(rep(.05, n.skills),
        seq(.8, .25, length.out = n.skills),
        skills[1:nrow(skills) %in% skills.selected, 3],
        adj = 0, cex = (skills.cex - 0.1), family = "Helvetica", font = 1
    )
}

# ---- Bottom right Events
{
    par(mar = c(0, 0, 0, 0))
    
    plot(0, 0,
        xlim = c(0, 1), ylim = c(0, 1), xaxt = "n", yaxt = "n",
        main = "", bty = "n", type = "n", xlab = "", ylab = ""
    )
    rect(xleft = -2, ybottom = 0.9, xright = 3, ytop = 1.5, col = "#F9B90A99", lwd = 0, border = NA)
    text(0.1, 0.95, "Compétences en lien avec le domaine d'étude", family = "Helvetica", cex = 1.3, adj = 0, font = 3)
    
    
    # Top label text
    # text(bottom.labels[3], side = 3, cex = 1.2, adj = .5, family = font.family)
    
    n.events <- length(events.selected)
    
    # Points
    points(rep(.02, n.events), seq(.75, .25, length.out = n.events), pch = 21, cex = 2.5, col = "blue", bg = "white")
    text(rep(.02, n.events), seq(.75, .25, length.out = n.events), events.selected, pch = 21, cex = .8, col = "black", bg = "white", family = "Helvetica")
    
    # Event text
    text(rep(.075, n.events),
        seq(.75, .25, length.out = n.events),
        events[1:nrow(events) %in% events.selected, 2],
        adj = 0, cex = events.cex, family = "Helvetica"
    )
}


# ----------
# Closing
# ----------
{
    if (google.font) {
    showtext::showtext.end()
    }
}
}
}